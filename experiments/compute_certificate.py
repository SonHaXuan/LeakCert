#!/usr/bin/env python3
"""
Certificate computation script (Section 3.3–3.4, Section 5.2).

Loads a fine-tuned model and a canary panel, computes:
  1. Per-canary KL estimates (Theorem 13 / Assumption 12)
  2. Hoeffding certificate (Theorem 10) for all query budgets
  3. Bernstein certificate (Theorem 13) as tighter alternative
  4. Certificate tightness ratio vs. empirical MI (Table 3)
  5. Extraction probability bound (Corollary 18)
  6. Prior-misspecification penalty (Table 4, Theorem 7)
  7. DP composition bound comparison (Table 8)

Output: JSON tables + human-readable summary.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.certificate import LeakageCertificate
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.model.backend_model import BackendCompletionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results")) / "certificate"
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    target_model_name = cfg["model"].get("target_model_small",
                                         cfg["model"].get("target_model", "local-test-model"))

    if not Path(target_path).exists():
        logger.error(f"Checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    # ── Load models ────────────────────────────────────────────────────
    logger.info(f"Loading target: {target_path}")
    target = BackendCompletionService(target_path, temperature=1.0, max_new_tokens=128)
    logger.info(f"Loading reference: {target_model_name}")
    ref = BackendCompletionService(target_model_name, temperature=1.0, max_new_tokens=128)

    # ── Generate canary panel ──────────────────────────────────────────
    n_per_type = cfg["canary"].get("n_eval_per_type", 283)
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=cfg["canary"]["seed"],
    )
    # Pass n_t3/n_t4 so T3/T4 counts match the eval panel size used by W4/W5.
    panel = gen.generate_panel(
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    # Certificate should cover all injected canaries — no split needed.
    train_panel = panel
    K = len(panel)

    # ── Compute KL estimates ───────────────────────────────────────────
    logger.info(f"Computing KL estimates for {len(train_panel)} canaries...")
    estimator = KLEstimator(target, ref)
    kl_results = estimator.estimate_panel(train_panel)

    kl_values = np.array([r.kl_estimate for r in kl_results])
    logger.info(
        f"KL stats: mean={kl_values.mean():.4f}, max={kl_values.max():.4f}, "
        f"std={kl_values.std():.4f}"
    )
    with open(output_dir / "kl_estimates.json", "w") as f:
        json.dump([
            {"canary_id": r.canary_id, "kl": r.kl_estimate,
             "log_p_target": r.log_p_target, "log_p_ref": r.log_p_ref,
             "type": r.canary_type}
            for r in kl_results
        ], f, indent=2)

    # ── Compute certificates (Theorem 10 + 13) ────────────────────────
    cert_computer = LeakageCertificate()
    budgets = cfg["certificate"].get(
        "budgets", [1, 10, 100, 1_000, 5_000, 10_000, 50_000, 100_000,
                    1_000_000, 10_000_000]
    )
    delta = cfg["certificate"].get("delta", 0.01)

    logger.info("\n=== Table 1: Worked-example certificates ===")
    logger.info(f"{'B':>12} {'cert (nats)':>14} {'P(K̂=K)':>12} {'throttled?':>12}")

    table1 = []
    for B in budgets:
        result = cert_computer.compute(kl_results, B, K, delta)
        emp_mi = KLEstimator.mine_estimate(kl_values.tolist(), B, K)
        tightness = result.hoeffding_certificate / emp_mi if emp_mi > 0 else float("inf")
        is_vac = LeakageCertificate.is_vacuous(result.hoeffding_certificate, K)
        ext_prob = result.extraction_prob_bound

        row = {
            "B": B,
            "hoeffding_cert_nats": round(result.hoeffding_certificate, 3),
            "bernstein_cert_nats": round(result.bernstein_certificate, 3),
            "empirical_mi_nats": round(emp_mi, 3),
            "tightness_ratio": round(tightness, 3) if not math.isinf(tightness) else None,
            "extraction_prob_bound": round(ext_prob, 6) if ext_prob else None,
            "vacuous": is_vac,
        }
        table1.append(row)

        logger.info(
            f"  {B:>10d} | {result.hoeffding_certificate:>12.3f} | "
            f"{(ext_prob or 0)*100:>10.4f}% | {'yes' if is_vac else 'no':>12}"
        )

    with open(output_dir / "table1_certificate.json", "w") as f:
        json.dump(table1, f, indent=2)

    # ── Table 3: Certificate tightness across budgets ─────────────────
    from leakcert.evaluation.metrics import compute_tightness_table
    tightness_table = compute_tightness_table(kl_results, budgets[:6], K, delta)
    logger.info("\n=== Table 3: Certificate tightness ===")
    for row in tightness_table:
        logger.info(f"  {row}")

    with open(output_dir / "table3_tightness.json", "w") as f:
        json.dump([
            {"B": r.query_budget, "cert_nats": r.certificate_nats,
             "emp_mi_nats": r.empirical_mi_nats, "ratio": r.ratio,
             "tight": r.is_tight}
            for r in tightness_table
        ], f, indent=2)

    # ── Table 4: Prior misspecification (Theorem 7) ────────────────────
    logger.info("\n=== Table 4: Prior misspecification penalty ===")
    B_ref = 10_000
    uniform_result = cert_computer.compute(kl_results, B_ref, K, delta)

    # Type-empirical prior (proportion of each canary type in K)
    from leakcert.canary.types import CanaryType
    type_counts = {t.value: 0 for t in CanaryType}
    for r in kl_results:
        type_counts[r.canary_type] = type_counts.get(r.canary_type, 0) + 1
    total = sum(type_counts.values())
    type_prior = [type_counts.get(r.canary_type, 1) / total for r in kl_results]
    type_result = cert_computer.compute(kl_results, B_ref, K, delta, prior=type_prior)

    table4 = [
        {"prior": "uniform", "H_K": round(math.log(K), 3),
         "D_KL_prior_unif": 0.0,
         "cert_nats": round(uniform_result.hoeffding_certificate, 1)},
        {"prior": "type-empirical",
         "H_K": round(type_result.prior_entropy, 3),
         "D_KL_prior_unif": round(
             type_result.prior_entropy - math.log(K) + uniform_result.hoeffding_certificate
             - type_result.hoeffding_certificate, 3),
         "cert_nats": round(type_result.hoeffding_certificate, 1)},
    ]
    logger.info(f"  {'Prior':<20} {'H(K)':>10} {'cert':>10}")
    for row in table4:
        logger.info(f"  {row['prior']:<20} {row['H_K']:>10.3f} {row['cert_nats']:>10.1f}")
    with open(output_dir / "table4_prior.json", "w") as f:
        json.dump(table4, f, indent=2)

    # ── Table 8: DP composition comparison ────────────────────────────
    logger.info("\n=== Table 8: DP vs. LeakCert certificate ===")
    dp_epsilons = cfg.get("evaluation", {}).get("dp_epsilons", [1, 2, 4, 8, 16])
    table8 = []
    baseline_cert = uniform_result.hoeffding_certificate
    for eps in dp_epsilons:
        dp_bound = LeakageCertificate.dp_composition_certificate(eps, B_ref, K)
        ratio = baseline_cert / dp_bound if dp_bound > 0 else float("inf")
        table8.append({
            "dp_epsilon": eps,
            "leakcert_nats": round(baseline_cert, 1),
            "dp_bound_nats": round(dp_bound, 1),
            "ratio_leakcert_dp": round(ratio, 3),
        })
        logger.info(
            f"  DP ε={eps:>2d}: LeakCert={baseline_cert:.1f} nats, "
            f"DP bound={dp_bound:.1f} nats, ratio={ratio:.3f}"
        )

    with open(output_dir / "table8_dp_comparison.json", "w") as f:
        json.dump(table8, f, indent=2)

    # ── Summary ───────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"Certificate summary (B=10^4, |K|={K}, δ={delta})")
    cert_10k = next((r for r in table1 if r["B"] == 10_000), None)
    if cert_10k:
        logger.info(f"  Hoeffding cert : {cert_10k['hoeffding_cert_nats']} nats")
        logger.info(f"  Tightness ratio: {cert_10k['tightness_ratio']}×")
        logger.info(f"  P(extract) ≤   : {cert_10k['extraction_prob_bound']:.4%}")
    logger.info(f"\nAll results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute LEAKCERT certificates")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    args = parser.parse_args()
    main(args)
