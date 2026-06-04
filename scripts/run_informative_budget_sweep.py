#!/usr/bin/env python3
"""Compute informative-budget certificate sweeps from saved KL estimates."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from leakcert.certificate.certificate import LeakageCertificate
from leakcert.certificate.kl_estimator import PerCanaryKL


ROOT = Path(__file__).resolve().parents[1]


def load_kl(path: Path) -> list[PerCanaryKL]:
    rows = json.loads(path.read_text())
    out = []
    for row in rows:
        out.append(
            PerCanaryKL(
                canary_id=str(row.get("canary_id", len(out))),
                kl_estimate=float(row.get("kl", row.get("kl_estimate", 0.0)) or 0.0),
                log_p_target=float(row.get("log_p_target", 0.0) or 0.0),
                log_p_ref=float(row.get("log_p_ref", 0.0) or 0.0),
                n_tokens=int(row.get("n_tokens", 1) or 1),
                canary_type=str(row.get("type", row.get("canary_type", "unknown"))),
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kl-estimates", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--budgets", default="1,2,5,10,25,50,100,200,400,600,800,1000,2000")
    parser.add_argument("--delta", type=float, default=0.01)
    args = parser.parse_args()

    kl_path = Path(args.kl_estimates)
    if not kl_path.is_absolute():
        kl_path = ROOT / kl_path
    out = ROOT / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    kl_results = load_kl(kl_path)
    budgets = [int(x) for x in args.budgets.split(",") if x.strip()]

    cert = LeakageCertificate()
    rows = []
    for B in budgets:
        result = cert.compute(kl_results, B, len(kl_results), args.delta)
        raw_c1 = (result.raw_hoeffding_certificate or result.hoeffding_certificate) / B
        b_star = result.prior_entropy / raw_c1 if raw_c1 > 0 else math.inf
        rows.append({
            "B": B,
            "n_canaries": len(kl_results),
            "H_K_nats": result.prior_entropy,
            "raw_C1_nats_per_query": raw_c1,
            "B_star": b_star,
            "B_over_B_star": B / b_star if math.isfinite(b_star) and b_star > 0 else 0.0,
            "raw_hoeffding_cert_nats": result.raw_hoeffding_certificate,
            "capped_hoeffding_cert_nats": result.hoeffding_certificate,
            "raw_bernstein_cert_nats": result.raw_bernstein_certificate,
            "capped_bernstein_cert_nats": result.bernstein_certificate,
            "entropy_cap_applied": result.entropy_cap_applied,
            "non_vacuous": result.hoeffding_certificate < result.prior_entropy - 1e-12,
            "mean_kl": result.mean_kl,
            "max_kl": result.max_kl,
            "std_kl": result.std_kl,
        })

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kl_estimates": str(kl_path.relative_to(ROOT)),
        "delta": args.delta,
        "n_rows": len(rows),
        "any_non_vacuous": any(row["non_vacuous"] for row in rows),
        "rows": rows,
    }
    (out / "informative_budget_sweep.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    md = [
        "# Informative-Budget Certificate Sweep",
        "",
        f"- KL source: `{summary['kl_estimates']}`",
        f"- n canaries: `{len(kl_results)}`",
        f"- any non-vacuous capped certificate: `{summary['any_non_vacuous']}`",
        "",
        "| B | B/B* | raw cert | capped cert | H(K) | cap applied | non-vacuous |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        md.append(
            f"| {row['B']} | {row['B_over_B_star']:.3f} | "
            f"{row['raw_hoeffding_cert_nats']:.3f} | {row['capped_hoeffding_cert_nats']:.3f} | "
            f"{row['H_K_nats']:.3f} | {row['entropy_cap_applied']} | {row['non_vacuous']} |"
        )
    (out / "informative_budget_sweep.md").write_text("\n".join(md) + "\n")
    print(json.dumps({
        "output_dir": str(out.relative_to(ROOT)),
        "n_rows": len(rows),
        "any_non_vacuous": summary["any_non_vacuous"],
        "first_B_star": rows[0]["B_star"] if rows else None,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
