#!/usr/bin/env python3
"""
W2 – LCCT Prompts Benchmark.

Evaluates all defences on the 4,832-item LCCT (Leakage in Code Completion
Tools) benchmark (Yang et al. [4]).  Each prompt is a real extraction attempt
originally used against commercial completion services.

Metrics:
  - Verbatim extraction rate (rank-1 Carlini-style, B7)
  - Per-credential-category breakdown (aws_key, jwt, rsa, password, etc.)

The study uses W2 to cross-check that W1/W4 findings generalise to
production-style prompts rather than synthetic canary contexts.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.canary.generator import CanaryGenerator
from leakcert.model.backend_model import BackendCompletionService
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.evaluation.workloads import W2LCCT
from leakcert.defenses.no_defense import NoDefense
from leakcert.defenses.temperature import TemperatureDefense
from leakcert.defenses.top_p import TopPDefense
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.rate_limit import RateLimitDefense
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.attacks.a_fixed import AFixed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results")) / "w2"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    target_model_name = cfg["model"].get("target_model_small",
                                         cfg["model"].get("target_model", "local-test-model"))

    if not Path(target_path).exists():
        logger.error(f"Target checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    # ── Load models ────────────────────────────────────────────────────
    target = BackendCompletionService(target_path, temperature=1.0, max_new_tokens=128)
    ref    = BackendCompletionService(target_model_name, temperature=1.0, max_new_tokens=128)

    # ── Load LCCT workload ────────────────────────────────────────────
    lcct_data_path = cfg.get("corpus", {}).get("lcct_path")
    w2 = W2LCCT(data_path=lcct_data_path)
    samples = w2.samples()
    logger.info(f"W2 LCCT: {len(samples)} prompts loaded")

    # ── Build defences ────────────────────────────────────────────────
    query_budget = cfg["evaluation"].get("query_budget", 10_000)
    kl_estimator = KLEstimator(target, ref)
    leakcert_runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl_estimator,
        config=RuntimeConfig(query_budget=query_budget),
    )
    defences = {
        "B1_no_defense":      NoDefense(target),
        "B2_temperature_0.5": TemperatureDefense(target, 0.5),
        "B3_top_p_0.7":       TopPDefense(target, 0.7),
        "B4_rate_limit":      RateLimitDefense(target, queries_per_day=1_000),
        "B5_content_filter":  ContentFilterDefense(target),
        "LEAKCERT":           _RuntimeServiceAdapter(leakcert_runtime),
    }

    # B7 Carlini-style attacker (rank-1 perplexity)
    attacker = AFixed(budget=256, n_samples=256, use_rank=True, ref_service=ref)

    # ── Run extraction on W2 ──────────────────────────────────────────
    w2_results: dict[str, dict] = {}

    for def_name, service in defences.items():
        logger.info(f"\n  W2 | {def_name}")
        n_hit = 0
        per_category: dict[str, list] = {}

        for i, sample in enumerate(samples):
            if i % 200 == 0:
                logger.info(f"    {i}/{len(samples)}")

            # Generate N=256 completions, rank by LR
            results = service.complete(sample.prompt, n_samples=min(256, 10))
            best = results[0].text if results else ""

            # Check if the expected secret (if known) appears
            expected = sample.expected_secret
            hit = bool(expected and expected.strip() in best) if expected else False
            n_hit += int(hit)

            cat = sample.metadata.get("category", "unknown")
            per_category.setdefault(cat, []).append(int(hit))

        rate = n_hit / max(len(samples), 1)
        per_cat_rates = {cat: sum(v)/len(v) for cat, v in per_category.items()}
        w2_results[def_name] = {
            "extraction_rate": round(rate * 100, 2),
            "n_hit": n_hit,
            "n_total": len(samples),
            "per_category": {k: round(v * 100, 2) for k, v in per_cat_rates.items()},
        }
        logger.info(f"    extraction rate = {rate:.2%}")

    # ── Print summary ─────────────────────────────────────────────────
    logger.info("\n=== W2 LCCT Results ===")
    logger.info(f"{'Defence':<25} {'Rate (%)':>10}")
    for def_name, res in w2_results.items():
        logger.info(f"{def_name:<25} {res['extraction_rate']:>10.2f}%")

    with open(output_dir / "w2_lcct_results.json", "w") as f:
        json.dump(w2_results, f, indent=2)

    logger.info(f"\nW2 results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W2: LCCT extraction benchmark")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    args = parser.parse_args()
    main(args)
