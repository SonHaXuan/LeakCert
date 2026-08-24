#!/usr/bin/env python3
"""
W4 – Code-Secret Extraction Suite.

Evaluation path A  — W4 workload prompts (len(eval_panel) × 7 unique prompts,
                      one query each, budget-independent).
Evaluation path B  — Adaptive attacker A-adaptive at B ∈ {10^2, 10^3, 10^4, 10^5}.

Both paths are saved to table2_extraction.json.
Each path uses an independent api_key for LEAKCERT so the W4 queries do NOT
drain the budget available to the adaptive attacker runs.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.attacks.a_adaptive import AAdaptive
from leakcert.attacks.a_greedy_lrt import AGreedyLRT
from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.defenses.temperature import TemperatureDefense
from leakcert.defenses.top_p import TopPDefense
from leakcert.evaluation.metrics import extraction_hit, rate_summary
from leakcert.evaluation.workloads import W4CodeSecret
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
    output_dir = Path(cfg.get("output_dir", "./results")) / "w4"
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_cfg = cfg.get("evaluation", {})
    query_budget = eval_cfg.get("query_budget", 10_000)
    batch_size = int(eval_cfg.get("batch_size", 8))

    table2_path = output_dir / "table2_extraction.json"

    def _flush_table2(w4_res, adaptive_res, defence_names):
        """Persist partial Table 2 after every stage so a wall-clock timeout
        never discards already-completed (path A / budget) results."""
        partial = {
            name: {
                "W4_workload": w4_res.get(name, {}),
                "A_adaptive": adaptive_res.get(name, {}),
            }
            for name in defence_names
        }
        with open(table2_path, "w") as f:
            json.dump(partial, f, indent=2)

    # ── Load models ───────────────────────────────────────────────────
    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    target_model_name = cfg["model"].get(
        "target_model_small", cfg["model"].get("target_model", "local-test-model")
    )
    logger.info(f"Loading target model from {target_path}")

    if not Path(target_path).exists():
        logger.error(f"Target checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    model_cfg = cfg.get("model", {})
    device = model_cfg.get("device", "auto")
    temperature = float(model_cfg.get("temperature", 1.0))
    max_new_tokens = int(model_cfg.get("max_new_tokens", 128))
    target = BackendCompletionService(
        target_path,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        device=device,
    )
    ref = BackendCompletionService(
        target_model_name,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        device=device,
    )

    # ── Generate eval panel (stratified subset of W1-injected panel) ────
    # Must use the same generate_panel(seed, n_t3, n_t4) call as W1 so the
    # eval canaries are guaranteed to be in the fine-tuned model's training set.
    # stratified_subset() then selects n_per_type per CanaryType in insertion
    # order — deterministic, balanced, and a true subset of the injected panel.
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
    logger.info(
        f"Eval panel: {len(eval_panel)} canaries ({n_per_type}/type × 4 types), "
        f"→ {len(eval_panel) * 7} unique W4 prompts"
    )

    # ── Build defences ────────────────────────────────────────────────
    kl_estimator = KLEstimator(target, ref)
    runtime_cfg = RuntimeConfig(query_budget=query_budget)
    leakcert_runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl_estimator,
        config=runtime_cfg,
        panel=eval_panel,
    )

    defences = {
        "B1_no_defense": NoDefense(target),
        "B2_temperature_0.5": TemperatureDefense(target, 0.5),
        "B3_top_p_0.7": TopPDefense(target, 0.7),
        "B5_content_filter": ContentFilterDefense(target),
    }

    # LEAKCERT defence (wrap runtime)
    from leakcert.evaluation.runner import _RuntimeServiceAdapter

    defences["LEAKCERT"] = _RuntimeServiceAdapter(leakcert_runtime)
    defences = select_defences(defences, eval_cfg.get("run_defenses"))
    logger.info("Enabled defences: %s", ", ".join(defences))

    # ── (A) W4 workload evaluation (budget-independent) ──────────────
    # Each (canary, template) pair queried exactly once.  For LEAKCERT,
    # use a dedicated api_key so these queries don't deplete the budget
    # that later attacker runs should see.
    logger.info("\n=== Path A: W4 workload prompts (one query per pair) ===")
    w4 = W4CodeSecret(panel=eval_panel)
    w4_samples = w4.samples()
    canary_by_id = {c.canary_id: c for c in eval_panel}
    logger.info(f"W4 workload: {len(w4_samples)} unique (canary, template) prompts")

    w4_results: dict[str, dict] = {}
    for def_name, service in defences.items():
        # Fresh api_key per defence so LEAKCERT budget is isolated.
        svc_w4 = (
            _RuntimeServiceAdapter(leakcert_runtime, api_key=f"w4_workload_{def_name}")
            if def_name == "LEAKCERT"
            else service
        )
        hits, total = 0, 0
        completions = complete_samples(svc_w4, w4_samples, batch_size)
        for sample, results in zip(w4_samples, completions):
            canary = canary_by_id.get(sample.canary_id)
            if canary is None:
                continue
            hit = extraction_hit(canary, results[0].text if results else "")
            hits += int(hit)
            total += 1
        rate = hits / max(total, 1)
        w4_results[def_name] = rate_summary(hits, total)
        logger.info(f"  {def_name:<25} W4 rate = {rate:.2%} ({hits}/{total})")
        _flush_table2(w4_results, {d: {} for d in defences}, defences)

    # ── (B) Adaptive attacker at multiple budgets ─────────────────────
    # Each (budget, defence) run gets its own api_key for isolation.
    logger.info("\n=== Path B: A-adaptive at multiple budgets ===")
    budgets = eval_cfg.get("adaptive_budgets", [100, 1_000, 10_000, 100_000])
    adaptive_results: dict[str, dict] = {d: {} for d in defences}

    for B in budgets:
        attacker = AAdaptive(budget=B)
        for def_name, service in defences.items():
            svc_atk = (
                _RuntimeServiceAdapter(
                    leakcert_runtime, api_key=f"adaptive_B{B}_{def_name}"
                )
                if def_name == "LEAKCERT"
                else service
            )
            logger.info(f"  W4 | B={B:>7d} | {def_name}")
            results = attacker.attack_panel(svc_atk, eval_panel)
            hits = sum(int(r.success) for r in results)
            summary = rate_summary(hits, len(results))
            adaptive_results[def_name][f"B={B}"] = summary
            rate = summary["rate"]
            logger.info(f"    extraction rate = {rate:.2%}")
            _flush_table2(w4_results, adaptive_results, defences)

    # ── Merge and print Table 2 ───────────────────────────────────────
    table2: dict[str, dict] = {}
    for def_name in defences:
        table2[def_name] = {
            "W4_workload": w4_results.get(def_name, {}),
            "A_adaptive": adaptive_results.get(def_name, {}),
        }

    logger.info("\n=== Table 2: Extraction Rates ===")
    header = f"{'Defence':<25}  {'W4 rate':>8}" + "".join(
        f"  {'B='+str(B):>8}" for B in budgets
    )
    logger.info(header)
    for def_name, row in table2.items():
        w4_r = row["W4_workload"].get("rate_pct", "-")
        atk_cols = "".join(
            f"  {row['A_adaptive'].get(f'B={B}', {}).get('rate_pct', '-'):>8}"
            for B in budgets
        )
        logger.info(f"{def_name:<25}  {w4_r:>7.2f}%{atk_cols}")

    with open(output_dir / "table2_extraction.json", "w") as f:
        json.dump(table2, f, indent=2)

    # ── Also run LRT attacker at B=10^4 (Table 11) ───────────────────
    if eval_cfg.get("run_attackers_lrt", True):
        logger.info("\n=== Table 11: A-greedy-LRT vs A-adaptive ===")
        lrt_results = {}
        for def_name, service in defences.items():
            a_adaptive = AAdaptive(budget=query_budget)
            a_lrt = AGreedyLRT(budget=query_budget, ref_service=ref)
            # Isolated api_keys so A-adaptive and A-LRT don't share budget.
            svc_adp = (
                _RuntimeServiceAdapter(
                    leakcert_runtime, api_key=f"lrt_adaptive_{def_name}"
                )
                if def_name == "LEAKCERT"
                else service
            )
            svc_lrt = (
                _RuntimeServiceAdapter(
                    leakcert_runtime, api_key=f"lrt_greedy_{def_name}"
                )
                if def_name == "LEAKCERT"
                else service
            )
            r_adp = a_adaptive.attack_panel(svc_adp, eval_panel)
            r_lrt = a_lrt.attack_panel(svc_lrt, eval_panel)
            lrt_results[def_name] = {
                "A_adaptive": round(a_adaptive.extraction_success_rate(r_adp) * 100, 2),
                "A_greedy_LRT": round(a_lrt.extraction_success_rate(r_lrt) * 100, 2),
            }
            logger.info(
                f"  {def_name}: adaptive={lrt_results[def_name]['A_adaptive']:.2f}% "
                f"LRT={lrt_results[def_name]['A_greedy_LRT']:.2f}%"
            )

        with open(output_dir / "table11_lrt.json", "w") as f:
            json.dump(lrt_results, f, indent=2)

    logger.info(f"\nW4 results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W4: Code-secret extraction suite")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    args = parser.parse_args()
    main(args)
