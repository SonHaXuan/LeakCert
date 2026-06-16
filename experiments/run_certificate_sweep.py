#!/usr/bin/env python3
"""
Small-budget certificate sweep (no GPU needed).

Reuses the per-canary KL estimates saved by experiments/compute_certificate.py
(kl_estimates.json) and recomputes the Theorem 10/13 certificates at small
query budgets B, looking for the non-vacuous regime B < B* = H(K)/C1.

Also sweeps per-canary-type sub-panels: each type has its own H(K)=ln(n_type)
and mean KL, so e.g. the weakly-memorized T4 panel (mean KL ~1.8 nats) can be
non-vacuous at budgets where the full panel is not.

Output: <output-dir>/certificate_sweep.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.certificate.certificate import LeakageCertificate
from leakcert.certificate.kl_estimator import PerCanaryKL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BUDGETS = [1, 2, 5, 10, 25, 50, 100, 250, 500, 1000]


def sweep(kl_results: list[PerCanaryKL], budgets: list[int], delta: float) -> list[dict]:
    cert = LeakageCertificate()
    K = len(kl_results)
    rows = []
    for B in budgets:
        r = cert.compute(kl_results, B, K, delta)
        # Vacuity must be judged on the RAW (uncapped) certificate against the
        # actual entropy ceiling H(K) used as the cap. Comparing the *capped*
        # value to math.log(K) produced a float artifact: when capped,
        # hoeffding_certificate == prior_entropy, which can round just below
        # math.log(K) and be misreported as non-vacuous. The raw value carries
        # no such ambiguity — if it reaches H(K) the bound is trivial.
        raw_h = (r.raw_hoeffding_certificate
                 if r.raw_hoeffding_certificate is not None
                 else r.hoeffding_certificate)
        vacuous = bool(raw_h >= r.prior_entropy - 1e-9)
        rows.append({
            "B": B,
            "hoeffding_cert_nats": round(r.hoeffding_certificate, 4),
            "bernstein_cert_nats": round(r.bernstein_certificate, 4),
            "raw_hoeffding_cert_nats": round(raw_h, 4),
            "entropy_H_K_nats": round(r.prior_entropy, 4),
            "entropy_cap_applied": bool(r.entropy_cap_applied),
            "extraction_prob_bound": (
                round(r.extraction_prob_bound, 6)
                if r.extraction_prob_bound is not None else None),
            "vacuous": vacuous,
        })
    return rows


def main(args):
    kl_rows = json.load(open(args.kl_estimates))
    kl_results = [
        PerCanaryKL(
            canary_id=row["canary_id"],
            kl_estimate=row["kl"],
            log_p_target=row.get("log_p_target", 0.0),
            log_p_ref=row.get("log_p_ref", 0.0),
            n_tokens=row.get("n_tokens", 0),   # metadata only; absent from saved JSON
            canary_type=row.get("type", ""),
        )
        for row in kl_rows
    ]
    logger.info(f"Loaded {len(kl_results)} KL estimates from {args.kl_estimates}")

    budgets = args.budgets or DEFAULT_BUDGETS
    out = {
        "source_kl_estimates": str(args.kl_estimates),
        "delta": args.delta,
        "full_panel": {
            "n": len(kl_results),
            "mean_kl_nats": round(
                sum(r.kl_estimate for r in kl_results) / len(kl_results), 4),
            "sweep": sweep(kl_results, budgets, args.delta),
        },
        "by_type": {},
    }

    types: dict[str, list[PerCanaryKL]] = {}
    for r in kl_results:
        types.setdefault(r.canary_type or "unknown", []).append(r)
    for t, subset in sorted(types.items()):
        out["by_type"][t] = {
            "n": len(subset),
            "mean_kl_nats": round(
                sum(r.kl_estimate for r in subset) / len(subset), 4),
            "sweep": sweep(subset, budgets, args.delta),
        }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "certificate_sweep.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    logger.info("=== Sweep summary (Hoeffding cert, nats; * = non-vacuous) ===")
    header = f"{'panel':<20}" + "".join(f" B={b:<6}" for b in budgets)
    logger.info(header)
    for name, block in [("full", out["full_panel"])] + list(out["by_type"].items()):
        cells = "".join(
            f" {row['hoeffding_cert_nats']:<7.2f}" + ("*" if not row["vacuous"] else " ")
            for row in block["sweep"]
        )
        logger.info(f"{name:<20}{cells}")
    logger.info(f"Saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Small-budget certificate sweep")
    parser.add_argument("--kl-estimates", required=True,
                        help="Path to kl_estimates.json from compute_certificate.py")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--delta", type=float, default=0.01)
    parser.add_argument("--budgets", type=int, nargs="*", default=None)
    args = parser.parse_args()
    main(args)
