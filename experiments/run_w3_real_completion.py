#!/usr/bin/env python3
"""
W3 – Real Completion (Utility Evaluation).

utility benchmark (820 problems) + task benchmark (399 problems).
Reports pass@1 and pass@10 for each defence configuration.

This workload is orthogonal to extraction — it measures the UTILITY cost
of each defence, enabling the utility-leakage Pareto front (Figure 4).

Key finding to verify:
  DP-SGD ε=8 (B6): pass@1 drops 34.2% → 22.9%  (−11.3pp)
  LEAKCERT:        pass@1 drops 34.2% → 33.0%   (−1.2pp)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.model.backend_model import BackendCompletionService
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.evaluation.workloads import W3RealCompletion
from leakcert.evaluation.metrics import UtilityMetrics, evaluate_pass_at_k
from leakcert.defenses.no_defense import NoDefense
from leakcert.defenses.temperature import TemperatureDefense
from leakcert.defenses.top_p import TopPDefense
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig
from leakcert.evaluation.runner import _RuntimeServiceAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results")) / "w3"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    target_model_name = cfg["model"].get("target_model_small",
                                         cfg["model"].get("target_model", "local-test-model"))

    if not Path(target_path).exists():
        logger.error(f"Target checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    # ── Load models ────────────────────────────────────────────────────
    target = BackendCompletionService(target_path, temperature=1.0, max_new_tokens=256)
    ref    = BackendCompletionService(target_model_name, temperature=1.0, max_new_tokens=256)

    # ── W3 workload ────────────────────────────────────────────────────
    w3_data = cfg.get("corpus", {}).get("utility_eval_path")
    w3 = W3RealCompletion(data_path=w3_data)
    logger.info(f"W3 utility benchmark: {len(w3.samples())} problems")

    # ── Build defences ─────────────────────────────────────────────────
    query_budget = cfg["evaluation"].get("query_budget", 10_000)
    kl_estimator = KLEstimator(target, ref)
    leakcert_runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl_estimator,
        config=RuntimeConfig(
            query_budget=query_budget,
            refusal_threshold=0.5,
        ),
    )

    defences = {
        "B1_no_defense":      NoDefense(target),
        "B2_temperature_0.5": TemperatureDefense(target, 0.5),
        "B3_top_p_0.7":       TopPDefense(target, 0.7),
        "B5_content_filter":  ContentFilterDefense(target),
        "LEAKCERT":           _RuntimeServiceAdapter(leakcert_runtime),
    }

    # If DP-SGD checkpoint exists, add B6
    dp_path = cfg.get("finetune_dp", {}).get("output_dir")
    if dp_path and Path(dp_path).exists():
        dp_service = BackendCompletionService(dp_path, temperature=1.0, max_new_tokens=256)
        defences["B6_DP_SGD_eps8"] = NoDefense(dp_service)
        logger.info(f"Added B6 DP-SGD model from {dp_path}")

    # ── Evaluate utility (pass@1) ──────────────────────────────────────
    utility_results: dict[str, dict] = {}

    logger.info("\n=== W3 Utility Evaluation (pass@1) ===")
    for def_name, service in defences.items():
        logger.info(f"  Evaluating: {def_name}")
        metrics = evaluate_pass_at_k(service, w3, k=1, n_samples=1, timeout=10.0)
        utility_results[def_name] = {
            "pass_at_1": round(metrics.pass_at_1 * 100, 1),
            "n_correct": metrics.n_correct_at_1,
            "n_problems": metrics.n_problems,
        }
        logger.info(f"    pass@1 = {metrics.pass_at_1:.1%}")

        # Measure refusal rate for LEAKCERT
        if def_name == "LEAKCERT":
            refusal_rate = leakcert_runtime.refusal_rate()
            latency = leakcert_runtime.latency_stats()
            utility_results[def_name]["refusal_rate"] = round(refusal_rate * 100, 2)
            utility_results[def_name]["latency_median_ms"] = round(latency["median"], 1)
            utility_results[def_name]["latency_p99_ms"] = round(latency["p99"], 1)
            logger.info(
                f"    refusal rate = {refusal_rate:.2%} | "
                f"latency median={latency['median']:.1f}ms p99={latency['p99']:.1f}ms"
            )

    # ── Print Table 7: Refusal rate + overhead ─────────────────────────
    logger.info("\n=== Table 7: Refusal rate and latency overhead ===")
    logger.info(f"{'Defence':<25} {'pass@1':>8} {'refusal%':>10} {'Δms(med)':>12}")
    for def_name, res in utility_results.items():
        logger.info(
            f"{def_name:<25} {res['pass_at_1']:>7.1f}%"
            f" {res.get('refusal_rate', 0.0):>9.2f}%"
            f" {res.get('latency_median_ms', 0.0):>11.1f}"
        )

    # ── Utility-leakage Pareto front data ──────────────────────────────
    # Requires leakage estimate at B=10^4; load from certificate results
    leakage_path = Path(cfg.get("output_dir", "./results")) / "certificate" / "table1_certificate.json"
    if leakage_path.exists():
        with open(leakage_path) as f:
            cert_data = json.load(f)
        leakage_at_1e4 = next(
            (r["hoeffding_cert_nats"] for r in cert_data if r.get("B") == 10_000),
            None
        )
        if leakage_at_1e4:
            for def_name in utility_results:
                utility_results[def_name]["leakage_nats_B1e4"] = leakage_at_1e4
            logger.info(
                f"\nPareto front point (LEAKCERT): "
                f"utility={utility_results.get('LEAKCERT', {}).get('pass_at_1', '?')}%"
                f" leakage={leakage_at_1e4:.1f} nats"
            )

    with open(output_dir / "w3_utility.json", "w") as f:
        json.dump(utility_results, f, indent=2)

    logger.info(f"\nW3 results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W3: Utility evaluation (utility benchmark)")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    args = parser.parse_args()
    main(args)
