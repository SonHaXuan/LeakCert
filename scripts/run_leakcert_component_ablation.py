#!/usr/bin/env python3
"""Ablate LEAKCERT runtime components on W4/W5 extraction."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.evaluation.metrics import extraction_hit, rate_summary
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W4CodeSecret, W5Paraphrase
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig

VARIANTS = {
    "LEAKCERT_full": {},
    "LEAKCERT_no_rate_limit": {"use_rate_limit": False},
    "LEAKCERT_no_accounting": {"use_accounting": False},
    "LEAKCERT_no_suppression": {"use_suppression": False},
    "LEAKCERT_no_refusal": {"use_refusal": False},
}


def make_panel(cfg: dict):
    n_per_type = int(cfg.get("canary", {}).get("n_eval_per_type", 8))
    gen = CanaryGenerator(
        n_canaries=int(cfg.get("canary", {}).get("n_canaries", 64)),
        n_eval=n_per_type * 4,
        seed=int(cfg.get("canary", {}).get("seed", cfg.get("seed", 0))),
    )
    panel = gen.generate_panel(
        include_paraphrase=bool(cfg.get("canary", {}).get("include_paraphrase", True)),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    return panel.stratified_subset(n_per_type)


def eval_workload(name: str, service, workload, panel, batch_size: int) -> dict:
    samples = workload.samples()
    canary_by_id = {c.canary_id: c for c in panel}
    started = time.time()
    completions = service.complete_many(
        [sample.prompt for sample in samples], n_samples=1, batch_size=batch_size
    )
    hits = 0
    refused = 0
    per_mode: dict[str, list[int]] = {}
    per_type: dict[str, list[int]] = {}
    rows = []
    for sample, comp_list in zip(samples, completions):
        canary = canary_by_id[sample.canary_id]
        comp = comp_list[0] if comp_list else None
        text = comp.text if comp else ""
        hit = extraction_hit(canary, text)
        hits += int(hit)
        refused += int(bool(getattr(comp, "was_refused", False)) if comp else False)
        mode = sample.paraphrase_mode or "direct"
        ctype = getattr(canary.canary_type, "value", str(canary.canary_type))
        per_mode.setdefault(mode, []).append(int(hit))
        per_type.setdefault(ctype, []).append(int(hit))
        rows.append(
            {
                "defense": name,
                "workload": workload.name,
                "prompt_id": sample.prompt_id,
                "canary_id": sample.canary_id,
                "mode": mode,
                "canary_type": ctype,
                "hit": bool(hit),
                "refused": bool(getattr(comp, "was_refused", False)) if comp else False,
            }
        )
    total = len(samples)
    return {
        "duration_sec": round(time.time() - started, 3),
        "extraction": rate_summary(hits, total),
        "refusal": rate_summary(refused, total),
        "per_mode": {
            k: rate_summary(sum(v), len(v)) for k, v in sorted(per_mode.items())
        },
        "per_type": {
            k: rate_summary(sum(v), len(v)) for k, v in sorted(per_type.items())
        },
        "rows": rows,
    }


def build_runtime(target, ref, panel, cfg: dict, overrides: dict) -> LeakCertRuntime:
    runtime_cfg = cfg.get("runtime", {})
    params = {
        "query_budget": int(
            runtime_cfg.get(
                "query_budget", cfg.get("evaluation", {}).get("query_budget", 200)
            )
        ),
        "refusal_threshold": float(runtime_cfg.get("refusal_threshold", 0.95)),
        "target_refusal_rate": float(runtime_cfg.get("target_refusal_rate", 0.02)),
        "refusal_model_path": runtime_cfg.get("refusal_model_path"),
        "use_learned_refusal": bool(runtime_cfg.get("use_learned_refusal", True)),
        "use_refusal_heuristics": bool(
            runtime_cfg.get("use_refusal_heuristics", False)
        ),
        "use_suppression": bool(runtime_cfg.get("use_suppression", True)),
        "use_canary_hashes": bool(runtime_cfg.get("use_canary_hashes", False)),
        "use_accounting": bool(runtime_cfg.get("use_accounting", True)),
        "use_rate_limit": bool(runtime_cfg.get("use_rate_limit", True)),
        "use_refusal": bool(runtime_cfg.get("use_refusal", True)),
    }
    params.update(overrides)
    return LeakCertRuntime(
        service=target,
        kl_estimator=KLEstimator(target, ref),
        config=RuntimeConfig(**params),
        panel=panel,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_cfg = cfg.get("model", {})
    target = BackendCompletionService(
        cfg["finetune"]["output_dir"],
        device=model_cfg.get("device", "auto"),
        temperature=float(model_cfg.get("temperature", 0.0)),
        max_new_tokens=int(model_cfg.get("max_new_tokens", 16)),
    )
    ref_name = (
        model_cfg.get("ref_model")
        or model_cfg.get("target_model_small")
        or model_cfg.get("target_model")
    )
    ref = BackendCompletionService(
        ref_name,
        device=model_cfg.get("device", "auto"),
        temperature=float(model_cfg.get("temperature", 0.0)),
        max_new_tokens=int(model_cfg.get("max_new_tokens", 16)),
    )
    panel = make_panel(cfg)
    workloads = {
        "W4": W4CodeSecret(panel),
        "W5": W5Paraphrase(W4CodeSecret(panel)),
    }
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "config": str(Path(args.config).resolve()),
            "target": cfg["finetune"]["output_dir"],
            "ref": ref_name,
            "n_eval": len(panel),
            "batch_size": args.batch_size,
        },
        "results": {},
    }
    with (out / "component_ablation_rows.jsonl").open("w", encoding="utf-8") as audit:
        services = {"B5_content_filter": ContentFilterDefense(target)}
        for name, overrides in VARIANTS.items():
            runtime = build_runtime(target, ref, panel, cfg, overrides)
            services[name] = _RuntimeServiceAdapter(runtime, api_key=name)
        for name, service in services.items():
            summary["results"][name] = {}
            for workload_name, workload in workloads.items():
                result = eval_workload(name, service, workload, panel, args.batch_size)
                for row in result.pop("rows"):
                    audit.write(json.dumps(row, sort_keys=True) + "\n")
                summary["results"][name][workload_name] = result
                (out / "component_ablation_partial.json").write_text(
                    json.dumps(summary, indent=2)
                )
                print(
                    json.dumps(
                        {
                            "defense": name,
                            "workload": workload_name,
                            **result["extraction"],
                        },
                        indent=2,
                    ),
                    flush=True,
                )
    (out / "component_ablation_summary.json").write_text(json.dumps(summary, indent=2))
    md = [
        "# LEAKCERT Component Ablation",
        "",
        f"Generated: `{summary['metadata']['timestamp']}`",
        "",
        "| variant | W4 extraction | W5 extraction | W5/W4 | W5 refusal |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, workloads_result in summary["results"].items():
        w4 = workloads_result["W4"]["extraction"]["rate_pct"]
        w5 = workloads_result["W5"]["extraction"]["rate_pct"]
        ref = workloads_result["W5"]["refusal"]["rate_pct"]
        ratio = w5 / w4 if w4 else 0.0
        md.append(f"| {name} | {w4:.2f}% | {w5:.2f}% | {ratio:.3f}x | {ref:.2f}% |")
    (out / "component_ablation_summary.md").write_text("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
