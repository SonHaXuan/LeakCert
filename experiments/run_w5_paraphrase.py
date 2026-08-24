#!/usr/bin/env python3
"""
W5 – Paraphrase-Attack Suite.

Produces Table 6: W5/W4 extraction ratio per defence.

Protocol:
  W4 baseline  — len(eval_panel) × 7 unique (canary, template) prompts,
                  one query each (budget-independent, NOT attacker-based).
  W5 prompts   — W4 × 5 paraphrase modes = len(eval_panel) × 35 unique triples.
  Ratio r = W5_rate / W4_rate.

Each of W4 and W5 uses a dedicated api_key for LEAKCERT so neither
measurement drains the other's budget.

Key finding to verify:
  B5 content filter: ~7.42× (brittle — regex bypass via paraphrase)
  LEAKCERT:          ~1.05× (robust — operates on KL divergence, not lexical form)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.defenses.temperature import TemperatureDefense
from leakcert.defenses.top_p import TopPDefense
from leakcert.evaluation.metrics import (
    ExtractionMetrics,
    extraction_hit,
    paraphrase_robustness_ratio,
    rate_summary,
)
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W4CodeSecret, W5Paraphrase
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def select_defences(defences: dict, requested: list[str] | None) -> dict:
    if not requested:
        return defences
    selected = {}
    for token in requested:
        token_upper = str(token).upper()
        for name, service in defences.items():
            if name.upper() == token_upper or name.upper().startswith(
                f"{token_upper}_"
            ):
                selected[name] = service
                break
    missing = [
        token
        for token in requested
        if not any(
            name.upper() == str(token).upper()
            or name.upper().startswith(f"{str(token).upper()}_")
            for name in defences
        )
    ]
    if missing:
        logger.warning(
            "Ignoring unknown run_defenses entries: %s", ", ".join(map(str, missing))
        )
    return selected or defences


def complete_samples(service, samples, batch_size: int):
    prompts = [sample.prompt for sample in samples]
    return service.complete_many(prompts, n_samples=1, batch_size=batch_size)


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results")) / "w5"
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_cfg = cfg.get("evaluation", {})
    query_budget = eval_cfg.get("query_budget", 10_000)
    batch_size = int(eval_cfg.get("batch_size", 8))
    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    target_model_name = cfg["model"].get(
        "target_model_small", cfg["model"].get("target_model", "local-test-model")
    )

    if not Path(target_path).exists():
        logger.error(f"Target checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    model_cfg = cfg.get("model", {})
    device = model_cfg.get("device", "auto")
    temperature = float(model_cfg.get("temperature", 1.0))
    target = BackendCompletionService(
        target_path,
        temperature=temperature,
        max_new_tokens=int(model_cfg.get("max_new_tokens", 128)),
        device=device,
    )
    ref = BackendCompletionService(
        target_model_name,
        temperature=temperature,
        max_new_tokens=int(model_cfg.get("max_new_tokens", 128)),
        device=device,
    )

    # ── Generate eval panel (stratified subset of W1-injected panel) ────
    # Same generate_panel() call as W1 (same seed + n_t3/n_t4) produces the
    # same deterministic panel.  stratified_subset() then picks n_per_type per
    # CanaryType in insertion order → eval_panel ⊂ W1-injected panel.
    n_per_type = cfg["canary"].get("n_eval_per_type", 283)
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=cfg["canary"]["seed"],
    )
    panel = gen.generate_panel(
        include_paraphrase=cfg["canary"].get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    eval_panel = panel.stratified_subset(n_per_type)
    logger.info(f"Eval panel: {len(eval_panel)} canaries ({n_per_type}/type × 4 types)")

    kl_estimator = KLEstimator(target, ref)
    runtime_cfg = cfg.get("runtime", {})
    leakcert_runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl_estimator,
        config=RuntimeConfig(
            query_budget=int(runtime_cfg.get("query_budget", query_budget)),
            kl_budget=runtime_cfg.get("kl_budget"),
            window_seconds=float(runtime_cfg.get("window_seconds", 10 * 24 * 3600)),
            refusal_threshold=float(runtime_cfg.get("refusal_threshold", 0.5)),
            use_learned_refusal=bool(runtime_cfg.get("use_learned_refusal", True)),
            use_refusal_heuristics=bool(
                runtime_cfg.get("use_refusal_heuristics", True)
            ),
            target_refusal_rate=float(runtime_cfg.get("target_refusal_rate", 0.01)),
            refusal_model_path=runtime_cfg.get("refusal_model_path"),
            use_suppression=bool(runtime_cfg.get("use_suppression", True)),
            use_canary_hashes=bool(runtime_cfg.get("use_canary_hashes", False)),
            use_accounting=bool(runtime_cfg.get("use_accounting", True)),
            use_rate_limit=bool(runtime_cfg.get("use_rate_limit", True)),
            use_refusal=bool(runtime_cfg.get("use_refusal", True)),
            audit_log_path=runtime_cfg.get("audit_log_path"),
        ),
        panel=eval_panel,
    )

    defences = {
        "B1_no_defense": NoDefense(target),
        "B2_temperature_0.5": TemperatureDefense(target, 0.5),
        "B3_top_p_0.7": TopPDefense(target, 0.7),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(leakcert_runtime),
    }
    defences = select_defences(defences, eval_cfg.get("run_defenses"))
    logger.info("Enabled defences: %s", ", ".join(defences))

    # ── Build workloads ────────────────────────────────────────────────
    w4_workload = W4CodeSecret(panel=eval_panel)
    w5_workload = W5Paraphrase(w4_workload)
    w4_samples = w4_workload.samples()
    w5_samples = w5_workload.samples()
    canary_by_id = {c.canary_id: c for c in eval_panel}

    logger.info(
        f"W4: {len(w4_samples)} unique (canary, template) prompts; "
        f"W5: {len(w5_samples)} unique (canary, template, mode) prompts"
    )

    table6 = {}
    audit_rows = []
    logger.info("\n=== Table 6: Paraphrase robustness (W5/W4 ratio) ===")
    logger.info(f"{'Defence':<25} {'W4 rate':>10} {'W5 rate':>10} {'Ratio':>8}")

    for def_name, service in defences.items():
        # Dedicated api_keys so W4 and W5 budgets are independent for LEAKCERT.
        svc_w4 = (
            _RuntimeServiceAdapter(leakcert_runtime, api_key=f"w5_w4_{def_name}")
            if def_name == "LEAKCERT"
            else service
        )
        svc_w5 = (
            _RuntimeServiceAdapter(leakcert_runtime, api_key=f"w5_w5_{def_name}")
            if def_name == "LEAKCERT"
            else service
        )

        # ── W4 baseline: one query per (canary, template) prompt ──────
        n_w4_hit, n_w4 = 0, 0
        w4_completions = complete_samples(svc_w4, w4_samples, batch_size)
        for sample, results in zip(w4_samples, w4_completions):
            canary = canary_by_id.get(sample.canary_id)
            if canary is None:
                continue
            completion = results[0].text if results else ""
            hit = extraction_hit(canary, completion)
            n_w4_hit += int(hit)
            n_w4 += 1
            audit_rows.append(
                {
                    "defense": def_name,
                    "workload": "W4",
                    "prompt_id": sample.prompt_id,
                    "canary_id": sample.canary_id,
                    "canary_type": canary.canary_type,
                    "paraphrase_mode": sample.paraphrase_mode,
                    "prompt": sample.prompt,
                    "completion": completion,
                    "hit": bool(hit),
                }
            )
        w4_rate = n_w4_hit / max(n_w4, 1)
        w4_metrics = ExtractionMetrics(
            n_total=max(n_w4, 1),
            n_success_verbatim=n_w4_hit,
            defense_name=def_name,
            workload_name="W4",
        )

        # ── W5: one query per (canary, template, mode) prompt ─────────
        n_w5_hit, n_w5 = 0, 0
        w5_by_mode: dict[str, list[bool]] = {}
        w5_completions = complete_samples(svc_w5, w5_samples, batch_size)
        for sample, results in zip(w5_samples, w5_completions):
            canary = canary_by_id.get(sample.canary_id)
            if canary is None:
                continue
            completion = results[0].text if results else ""
            hit = extraction_hit(canary, completion)
            n_w5_hit += int(hit)
            n_w5 += 1
            mode = sample.paraphrase_mode or "unknown"
            w5_by_mode.setdefault(mode, []).append(hit)
            audit_rows.append(
                {
                    "defense": def_name,
                    "workload": "W5",
                    "prompt_id": sample.prompt_id,
                    "canary_id": sample.canary_id,
                    "canary_type": canary.canary_type,
                    "paraphrase_mode": sample.paraphrase_mode,
                    "prompt": sample.prompt,
                    "completion": completion,
                    "hit": bool(hit),
                }
            )

        w5_metrics = ExtractionMetrics(
            n_total=max(n_w5, 1),
            n_success_verbatim=n_w5_hit,
            defense_name=def_name,
            workload_name="W5",
        )

        ratio = paraphrase_robustness_ratio(w4_metrics, w5_metrics)
        per_mode = {m: rate_summary(sum(v), len(v)) for m, v in w5_by_mode.items()}
        w4_summary = rate_summary(n_w4_hit, n_w4)
        w5_summary = rate_summary(n_w5_hit, n_w5)
        table6[def_name] = {
            "w4_rate": w4_summary["rate_pct"],
            "w4_summary": w4_summary,
            "w5_rate": w5_summary["rate_pct"],
            "w5_summary": w5_summary,
            "ratio": round(ratio, 3),
            "per_mode": per_mode,
        }
        logger.info(
            f"{def_name:<25} {w4_rate*100:>9.2f}%"
            f" {w5_metrics.verbatim_rate*100:>9.2f}%"
            f" {ratio:>7.3f}×"
        )

    with open(output_dir / "table6_paraphrase_robustness.json", "w") as f:
        json.dump(table6, f, indent=2)
    with open(output_dir / "audit_samples.jsonl", "w") as f:
        f.writelines(json.dumps(row) + "\n" for row in audit_rows)

    logger.info(f"\nW5 results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W5: Paraphrase-attack suite")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    args = parser.parse_args()
    main(args)
