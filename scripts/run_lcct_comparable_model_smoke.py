#!/usr/bin/env python3
"""Run a small LCCT-comparable model evaluation and score completions."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig
from scripts.score_lcct_comparable import score_row, summarize


def load_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-model-path", required=True)
    parser.add_argument("--ref-model", default="Qwen/Qwen2.5-Coder-0.5B")
    parser.add_argument("--device", default="mps")
    parser.add_argument("--max-prompts", type=int, default=140)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--defenses", default="B1,B5,LEAKCERT")
    parser.add_argument("--refusal-model-path")
    parser.add_argument("--refusal-threshold", type=float, default=0.95)
    args = parser.parse_args()

    started = time.time()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.benchmark, out / "benchmark_subset_source.jsonl")

    benchmark = load_jsonl(Path(args.benchmark), args.max_prompts)
    target = BackendCompletionService(
        args.target_model_path,
        device=args.device,
        temperature=0.0,
        max_new_tokens=args.max_new_tokens,
    )
    ref = BackendCompletionService(
        args.ref_model,
        device=args.device,
        temperature=0.0,
        max_new_tokens=args.max_new_tokens,
    )
    runtime = LeakCertRuntime(
        service=target,
        kl_estimator=KLEstimator(target, ref),
        config=RuntimeConfig(
            query_budget=max(args.max_prompts * 2, 200),
            refusal_threshold=args.refusal_threshold,
            refusal_model_path=args.refusal_model_path,
            use_learned_refusal=bool(args.refusal_model_path),
            use_refusal_heuristics=not bool(args.refusal_model_path),
            use_suppression=True,
        ),
    )
    all_defenses = {
        "B1_no_defense": NoDefense(target),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(runtime, api_key="lcct_comparable_smoke"),
    }
    requested = {
        "B1": "B1_no_defense",
        "B5": "B5_content_filter",
        "LEAKCERT": "LEAKCERT",
    }
    defense_names = [
        requested[x.strip()] for x in args.defenses.split(",") if x.strip() in requested
    ]

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "benchmark": str(Path(args.benchmark)),
        "target_model_path": str(Path(args.target_model_path)),
        "ref_model": args.ref_model,
        "device": args.device,
        "max_prompts": args.max_prompts,
        "n_prompts": len(benchmark),
        "max_new_tokens": args.max_new_tokens,
        "batch_size": args.batch_size,
        "defenses": {},
    }
    for name in defense_names:
        service = all_defenses[name]
        completions = []
        scored = []
        t0 = time.time()
        batch_size = max(1, args.batch_size)
        for start in range(0, len(benchmark), batch_size):
            batch = benchmark[start : start + batch_size]
            results = service.complete_many(
                [row["prompt"] for row in batch],
                n_samples=1,
                batch_size=batch_size,
            )
            for row, result in zip(batch, results):
                text = result[0].text if result else ""
                completions.append({"id": row["id"], "completion": text})
                scored.append(score_row(row, text))
            completed = min(start + len(batch), len(benchmark))
            if completed % 25 == 0 or completed == len(benchmark):
                print(
                    json.dumps(
                        {
                            "defense": name,
                            "completed": completed,
                            "total": len(benchmark),
                        }
                    ),
                    flush=True,
                )
        ddir = out / name
        ddir.mkdir(exist_ok=True)
        write_jsonl(ddir / "completions.jsonl", completions)
        write_jsonl(ddir / "scored_rows.jsonl", scored)
        ds = summarize(scored)
        ds["duration_sec"] = time.time() - t0
        if name == "LEAKCERT":
            ds["refusal_rate_pct"] = round(runtime.refusal_rate() * 100.0, 2)
            ds["latency"] = runtime.latency_stats()
        summary["defenses"][name] = ds
        (ddir / "summary.json").write_text(
            json.dumps(ds, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps({"defense": name, **ds}, indent=2, sort_keys=True), flush=True)

    summary["duration_sec"] = time.time() - started
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    md = [
        "# LCCT Comparable Model Smoke",
        "",
        f"- benchmark: `{summary['benchmark']}`",
        f"- n prompts: `{summary['n_prompts']}`",
        f"- target: `{summary['target_model_path']}`",
        "",
        "| defense | hits | n | hit rate | refusal |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in summary["defenses"].items():
        md.append(
            f"| {name} | {row['hits']} | {row['n']} | {row['hit_rate_pct']}% | "
            f"{row.get('refusal_rate_pct', 0.0)}% |"
        )
    (out / "summary.md").write_text("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
