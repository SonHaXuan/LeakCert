#!/usr/bin/env python3
"""Bootstrap W5 extraction evidence from saved audit samples."""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import platform
import random
import socket
import time
from pathlib import Path


def load_hits(path: Path, *, defense: str, workload: str = "W5") -> list[int]:
    hits: list[int] = []
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("defense") != defense or row.get("workload") != workload:
                continue
            hits.append(1 if row.get("hit") else 0)
    if not hits:
        raise ValueError(f"No rows for defense={defense} workload={workload} in {path}")
    return hits


def bootstrap_worker(args: tuple[int, list[int], list[int], int]) -> list[float]:
    seed, a, b, n_boot = args
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    out: list[float] = []
    for _ in range(n_boot):
        ra = sum(a[rng.randrange(na)] for _ in range(na)) / na
        rb = sum(b[rng.randrange(nb)] for _ in range(nb)) / nb
        out.append(ra - rb)
    return out


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return math.nan
    idx = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * q))))
    return xs[idx]


def summarize_pair(
    *,
    label: str,
    baseline_path: Path,
    baseline_defense: str,
    method_path: Path,
    method_defense: str,
    n_boot: int,
    workers: int,
) -> dict:
    baseline = load_hits(baseline_path, defense=baseline_defense)
    method = load_hits(method_path, defense=method_defense)
    baseline_rate = sum(baseline) / len(baseline)
    method_rate = sum(method) / len(method)
    diff = baseline_rate - method_rate

    chunks = [n_boot // workers] * workers
    for i in range(n_boot % workers):
        chunks[i] += 1
    tasks = [
        (10_000 + i, baseline, method, chunks[i])
        for i in range(workers)
        if chunks[i] > 0
    ]
    with mp.Pool(processes=workers) as pool:
        samples = [x for chunk in pool.map(bootstrap_worker, tasks) for x in chunk]
    samples.sort()
    return {
        "label": label,
        "baseline": {
            "path": str(baseline_path),
            "defense": baseline_defense,
            "rate_pct": round(baseline_rate * 100.0, 3),
            "n": len(baseline),
            "hits": sum(baseline),
        },
        "method": {
            "path": str(method_path),
            "defense": method_defense,
            "rate_pct": round(method_rate * 100.0, 3),
            "n": len(method),
            "hits": sum(method),
        },
        "baseline_minus_method_pct": round(diff * 100.0, 3),
        "ci95_pct": [
            round(percentile(samples, 0.025) * 100.0, 3),
            round(percentile(samples, 0.975) * 100.0, 3),
        ],
        "p_baseline_gt_method": round(sum(1 for x in samples if x > 0) / len(samples), 5),
        "n_boot": len(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--n-boot", type=int, default=100_000)
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    seed43_audit = Path("_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/w5/audit_samples.jsonl")
    seed42_audit = Path("_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/audit_samples.jsonl")
    calibrated_aggressive = Path("_run_results/local_mps_leakcert_calibrated_w5_20260603_111430/w5/audit_samples.jsonl")
    calibrated_soft = Path("_run_results/local_mps_leakcert_calibrated_softheur_t095_w5_20260603_1145/w5/audit_samples.jsonl")
    learnedonly_t095 = Path("_run_results/local_mps_leakcert_learnedonly_w5_20260603_1158/threshold_0.95/w5/audit_samples.jsonl")
    learnedonly_seed42_t095 = Path("_run_results/learnedonly_t095_validation_20260603_190245/w5_seed42_t095/w5/audit_samples.jsonl")

    pairs = [
        {
            "label": "seed43_B5_vs_LEAKCERT",
            "baseline_path": seed43_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": seed43_audit,
            "method_defense": "LEAKCERT",
        },
        {
            "label": "seed42_B5_vs_LEAKCERT",
            "baseline_path": seed42_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": seed42_audit,
            "method_defense": "LEAKCERT",
        },
        {
            "label": "seed43_B5_vs_calibrated_aggressive",
            "baseline_path": seed43_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": calibrated_aggressive,
            "method_defense": "LEAKCERT",
        },
        {
            "label": "seed43_B5_vs_calibrated_softheur_t095",
            "baseline_path": seed43_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": calibrated_soft,
            "method_defense": "LEAKCERT",
        },
        {
            "label": "seed43_B5_vs_learnedonly_t095",
            "baseline_path": seed43_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": learnedonly_t095,
            "method_defense": "LEAKCERT",
        },
        {
            "label": "seed42_B5_vs_learnedonly_t095",
            "baseline_path": seed42_audit,
            "baseline_defense": "B5_content_filter",
            "method_path": learnedonly_seed42_t095,
            "method_defense": "LEAKCERT",
        },
    ]
    rows = [
        summarize_pair(n_boot=args.n_boot, workers=args.workers, **pair)
        for pair in pairs
    ]
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "n_boot": args.n_boot,
            "workers": args.workers,
            "duration_sec": time.time() - started,
        },
        "rows": rows,
    }
    (output_dir / "bootstrap_w5_evidence.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# Bootstrap W5 Evidence",
        "",
        f"Generated: `{summary['metadata']['timestamp']}`",
        f"Workers: `{args.workers}`, bootstrap samples per comparison: `{args.n_boot}`",
        "",
        "| comparison | baseline W5 | method W5 | baseline-method | 95% CI | P(baseline > method) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['baseline']['rate_pct']:.3f}% | "
            f"{row['method']['rate_pct']:.3f}% | "
            f"{row['baseline_minus_method_pct']:.3f} pp | "
            f"[{row['ci95_pct'][0]:.3f}, {row['ci95_pct'][1]:.3f}] | "
            f"{row['p_baseline_gt_method']:.5f} |"
        )
    (output_dir / "bootstrap_w5_evidence.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output_dir": str(output_dir), "duration_sec": summary["metadata"]["duration_sec"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
