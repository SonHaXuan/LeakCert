#!/usr/bin/env python3
"""Bootstrap multi-seed W5 evidence from saved audit rows."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import statistics
import time
from pathlib import Path
from typing import Any


DEFAULT_SEEDS = [
    {
        "seed": 42,
        "baseline": "_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/audit_samples.jsonl",
        "method": "_run_results/learnedonly_t095_validation_20260603_190245/w5_seed42_t095/w5/audit_samples.jsonl",
    },
    {
        "seed": 43,
        "baseline": "_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/w5/audit_samples.jsonl",
        "method": "_run_results/local_mps_leakcert_learnedonly_w5_20260603_1158/threshold_0.95/w5/audit_samples.jsonl",
    },
    {
        "seed": 44,
        "baseline": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed44/w5/audit_samples.jsonl",
        "method": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed44/w5/audit_samples.jsonl",
    },
    {
        "seed": 45,
        "baseline": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed45/w5/audit_samples.jsonl",
        "method": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed45/w5/audit_samples.jsonl",
    },
    {
        "seed": 46,
        "baseline": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed46/w5/audit_samples.jsonl",
        "method": "_run_results/mac_studio_stable_queue_20260604_131501/w5_seed46/w5/audit_samples.jsonl",
    },
]


def load_hits(path: Path, defense: str) -> list[int]:
    hits = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("workload") == "W5" and row.get("defense") == defense:
                hits.append(1 if row.get("hit") else 0)
    if not hits:
        raise ValueError(f"no W5 rows for {defense} in {path}")
    return hits


def percentile(xs: list[float], q: float) -> float:
    idx = max(0, min(len(xs) - 1, round((len(xs) - 1) * q)))
    return xs[idx]


def boot_worker(args: tuple[int, list[int], list[int], int]) -> list[float]:
    seed, baseline, method, n_boot = args
    rng = random.Random(seed)
    nb = len(baseline)
    nm = len(method)
    out = []
    for _ in range(n_boot):
        rb = sum(baseline[rng.randrange(nb)] for _ in range(nb)) / nb
        rm = sum(method[rng.randrange(nm)] for _ in range(nm)) / nm
        out.append(rb - rm)
    return out


def bootstrap_diff(baseline: list[int], method: list[int], n_boot: int, workers: int) -> dict[str, Any]:
    chunks = [n_boot // workers] * workers
    for i in range(n_boot % workers):
        chunks[i] += 1
    tasks = [(30_000 + i, baseline, method, chunks[i]) for i in range(workers) if chunks[i]]
    with mp.Pool(processes=workers) as pool:
        samples = [x for chunk in pool.map(boot_worker, tasks) for x in chunk]
    samples.sort()
    diff = sum(baseline) / len(baseline) - sum(method) / len(method)
    return {
        "baseline_minus_method_pct": round(diff * 100.0, 3),
        "ci95_pct": [round(percentile(samples, 0.025) * 100.0, 3), round(percentile(samples, 0.975) * 100.0, 3)],
        "p_baseline_gt_method": round(sum(1 for x in samples if x > 0) / len(samples), 5),
        "n_boot": len(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--n-boot", type=int, default=500_000)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    rows = []
    all_baseline: list[int] = []
    all_method: list[int] = []
    for spec in DEFAULT_SEEDS:
        baseline = load_hits(Path(spec["baseline"]), "B5_content_filter")
        method = load_hits(Path(spec["method"]), "LEAKCERT")
        all_baseline.extend(baseline)
        all_method.extend(method)
        boot = bootstrap_diff(baseline, method, args.n_boot, args.workers)
        rows.append(
            {
                "seed": spec["seed"],
                "baseline_path": spec["baseline"],
                "method_path": spec["method"],
                "baseline_rate_pct": round(sum(baseline) / len(baseline) * 100.0, 3),
                "method_rate_pct": round(sum(method) / len(method) * 100.0, 3),
                "baseline_hits": sum(baseline),
                "method_hits": sum(method),
                "n_baseline": len(baseline),
                "n_method": len(method),
                **boot,
            }
        )
    aggregate = bootstrap_diff(all_baseline, all_method, args.n_boot, args.workers)
    aggregate.update(
        {
            "baseline_rate_pct": round(sum(all_baseline) / len(all_baseline) * 100.0, 3),
            "method_rate_pct": round(sum(all_method) / len(all_method) * 100.0, 3),
            "baseline_hits": sum(all_baseline),
            "method_hits": sum(all_method),
            "n_baseline": len(all_baseline),
            "n_method": len(all_method),
            "seed_diff_mean_pct": round(statistics.mean(row["baseline_minus_method_pct"] for row in rows), 3),
            "seed_diff_median_pct": round(statistics.median(row["baseline_minus_method_pct"] for row in rows), 3),
        }
    )
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "n_boot": args.n_boot,
            "workers": args.workers,
            "duration_sec": round(time.time() - started, 3),
        },
        "comparison": "B5_content_filter minus LEAKCERT learned-only/refusal-calibrated W5 extraction",
        "rows": rows,
        "aggregate": aggregate,
    }
    (out / "bootstrap_w5_multiseed.json").write_text(json.dumps(summary, indent=2))
    md = [
        "# Multi-Seed W5 Bootstrap Evidence",
        "",
        f"Generated: `{summary['metadata']['timestamp']}`",
        "",
        "| seed | B5 W5 | LEAKCERT W5 | diff | 95% CI | P(B5 > LEAKCERT) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(
            f"| {row['seed']} | {row['baseline_rate_pct']:.3f}% | {row['method_rate_pct']:.3f}% | "
            f"{row['baseline_minus_method_pct']:.3f} pp | [{row['ci95_pct'][0]:.3f}, {row['ci95_pct'][1]:.3f}] | "
            f"{row['p_baseline_gt_method']:.5f} |"
        )
    md.extend(
        [
            "",
            "## Aggregate",
            "",
            f"- B5 W5: `{aggregate['baseline_rate_pct']:.3f}%` ({aggregate['baseline_hits']}/{aggregate['n_baseline']})",
            f"- LEAKCERT W5: `{aggregate['method_rate_pct']:.3f}%` ({aggregate['method_hits']}/{aggregate['n_method']})",
            f"- Difference: `{aggregate['baseline_minus_method_pct']:.3f} pp`",
            f"- 95% CI: `[{aggregate['ci95_pct'][0]:.3f}, {aggregate['ci95_pct'][1]:.3f}]`",
            f"- P(B5 > LEAKCERT): `{aggregate['p_baseline_gt_method']:.5f}`",
        ]
    )
    (out / "bootstrap_w5_multiseed.md").write_text("\n".join(md) + "\n")
    print(json.dumps({"output_dir": str(out), "aggregate": aggregate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
