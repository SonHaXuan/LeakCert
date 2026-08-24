#!/usr/bin/env python3
"""Evaluate LEAKCERT W3 utility/refusal for a refusal-threshold sweep."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.evaluation.metrics import evaluate_pass_at_k
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W3RealCompletion
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig


def make_panel(cfg: dict):
    n_per_type = cfg["canary"].get("n_eval_per_type", 8)
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
    return panel.stratified_subset(n_per_type)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--thresholds", default="0.7,0.8,0.9,0.95")
    parser.add_argument("--max-problems", type=int, default=40)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    model_cfg = cfg.get("model", {})
    target = BackendCompletionService(
        cfg["finetune"]["output_dir"],
        device=model_cfg.get("device", "auto"),
        temperature=1.0,
        max_new_tokens=64,
    )
    ref_name = model_cfg.get("target_model_small", model_cfg.get("target_model"))
    ref = BackendCompletionService(
        ref_name,
        device=model_cfg.get("device", "auto"),
        temperature=1.0,
        max_new_tokens=64,
    )
    kl = KLEstimator(target, ref)
    panel = make_panel(cfg)

    samples = W3RealCompletion(multilingual=False).samples()[: args.max_problems]

    class LimitedWorkload:
        def samples(self):
            return samples

    base_runtime = cfg.get("runtime", {})
    rows = {}
    for threshold in [float(x) for x in args.thresholds.split(",") if x.strip()]:
        runtime = LeakCertRuntime(
            service=target,
            kl_estimator=kl,
            config=RuntimeConfig(
                query_budget=int(base_runtime.get("query_budget", 200)),
                refusal_threshold=threshold,
                use_learned_refusal=bool(base_runtime.get("use_learned_refusal", True)),
                use_refusal_heuristics=bool(
                    base_runtime.get("use_refusal_heuristics", True)
                ),
                target_refusal_rate=float(
                    base_runtime.get("target_refusal_rate", 0.01)
                ),
                refusal_model_path=base_runtime.get("refusal_model_path"),
                use_suppression=bool(base_runtime.get("use_suppression", True)),
                use_canary_hashes=bool(base_runtime.get("use_canary_hashes", False)),
            ),
            panel=panel,
        )
        t0 = time.time()
        metrics = evaluate_pass_at_k(
            _RuntimeServiceAdapter(runtime, api_key=f"w3_threshold_{threshold}"),
            LimitedWorkload(),
            k=1,
            n_samples=1,
            timeout=5.0,
        )
        rows[str(threshold)] = {
            "duration_sec": time.time() - t0,
            "pass_at_1_pct": round(metrics.pass_at_1 * 100.0, 2),
            "n_correct_at_1": metrics.n_correct_at_1,
            "n_problems": metrics.n_problems,
            "refusal_rate_pct": round(runtime.refusal_rate() * 100.0, 2),
            "latency": runtime.latency_stats(),
        }
        print(
            json.dumps({"threshold": threshold, **rows[str(threshold)]}, indent=2),
            flush=True,
        )

    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "config": str(Path(args.config).resolve()),
            "max_problems": args.max_problems,
            "duration_sec": time.time() - started,
        },
        "rows": rows,
    }
    (output_dir / "w3_refusal_threshold_sweep.json").write_text(
        json.dumps(summary, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
