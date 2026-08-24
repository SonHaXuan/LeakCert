#!/usr/bin/env python3
"""Run W3 per-task error analysis for B1/B5/LEAKCERT."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W3RealCompletion
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig


def run_tests(
    prompt: str, completion: str, metadata: dict, timeout: float
) -> tuple[bool, str]:
    test_code = metadata.get("test", "")
    if not test_code:
        return False, "missing_test"
    code = prompt + completion + "\n\n" + test_code
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(code)
        tmp = handle.name
    try:
        proc = subprocess.run(
            [sys.executable, tmp], capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode == 0:
            return True, ""
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, err[-1][:500] if err else f"returncode={proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    finally:
        Path(tmp).unlink(missing_ok=True)


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


def build_workload(cfg: dict, max_problems: int):
    corpus = cfg.get("corpus", {})
    workload = W3RealCompletion(
        data_path=corpus.get("utility_eval_path") or None,
        subset=corpus.get("utility_subset", "utility_eval"),
        multilingual=bool(corpus.get("utility_multilingual", False)),
    )
    return workload.samples()[:max_problems]


def evaluate_defense(
    name: str, service, samples, timeout: float, batch_size: int, workers: int
) -> dict:
    started = time.time()
    completions = service.complete_many(
        [sample.prompt for sample in samples], n_samples=1, batch_size=batch_size
    )

    def check(args):
        sample, comp_list = args
        comp = comp_list[0] if comp_list else None
        text = comp.text if comp else ""
        passed, error = run_tests(sample.prompt, text, sample.metadata, timeout)
        return {
            "defense": name,
            "prompt_id": sample.prompt_id,
            "task_id": sample.metadata.get("task_id", sample.prompt_id),
            "dataset": sample.metadata.get("dataset", "unknown"),
            "language": sample.metadata.get("language", "unknown"),
            "passed": passed,
            "was_refused": bool(getattr(comp, "was_refused", False)) if comp else False,
            "refusal_reason": getattr(comp, "refusal_reason", None) if comp else None,
            "error": error,
            "completion_chars": len(text),
        }

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = list(pool.map(check, zip(samples, completions)))
    n_passed = sum(1 for row in rows if row["passed"])
    n_refused = sum(1 for row in rows if row["was_refused"])
    by_error: dict[str, int] = {}
    for row in rows:
        if row["passed"]:
            continue
        key = row["error"] or "failed"
        by_error[key] = by_error.get(key, 0) + 1
    return {
        "duration_sec": round(time.time() - started, 3),
        "n": len(rows),
        "n_passed": n_passed,
        "pass_at_1_pct": round(n_passed / max(len(rows), 1) * 100.0, 2),
        "n_refused": n_refused,
        "refusal_rate_pct": round(n_refused / max(len(rows), 1) * 100.0, 2),
        "top_errors": sorted(by_error.items(), key=lambda kv: kv[1], reverse=True)[:20],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-problems", type=int, default=164)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_cfg = cfg.get("model", {})
    target_path = cfg["finetune"]["output_dir"]
    ref_name = (
        model_cfg.get("ref_model")
        or model_cfg.get("target_model_small")
        or model_cfg.get("target_model")
    )
    device = model_cfg.get("device", "auto")
    max_new_tokens = int(model_cfg.get("max_new_tokens", 16))
    temperature = float(model_cfg.get("temperature", 0.0))

    target = BackendCompletionService(
        target_path,
        device=device,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
    )
    ref = BackendCompletionService(
        ref_name, device=device, temperature=temperature, max_new_tokens=max_new_tokens
    )
    panel = make_panel(cfg)
    runtime_cfg = cfg.get("runtime", {})
    runtime = LeakCertRuntime(
        service=target,
        kl_estimator=KLEstimator(target, ref),
        config=RuntimeConfig(
            query_budget=int(
                runtime_cfg.get(
                    "query_budget", cfg.get("evaluation", {}).get("query_budget", 200)
                )
            ),
            refusal_threshold=float(runtime_cfg.get("refusal_threshold", 0.95)),
            target_refusal_rate=float(runtime_cfg.get("target_refusal_rate", 0.02)),
            refusal_model_path=runtime_cfg.get("refusal_model_path"),
            use_learned_refusal=bool(runtime_cfg.get("use_learned_refusal", True)),
            use_refusal_heuristics=bool(
                runtime_cfg.get("use_refusal_heuristics", False)
            ),
            use_suppression=bool(runtime_cfg.get("use_suppression", True)),
            use_canary_hashes=bool(runtime_cfg.get("use_canary_hashes", False)),
            use_accounting=bool(runtime_cfg.get("use_accounting", True)),
            use_rate_limit=bool(runtime_cfg.get("use_rate_limit", True)),
            use_refusal=bool(runtime_cfg.get("use_refusal", True)),
        ),
        panel=panel,
    )
    samples = build_workload(cfg, args.max_problems)
    defenses = {
        "B1_no_defense": NoDefense(target),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(runtime, api_key="w3_error_analysis"),
    }
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "config": str(Path(args.config).resolve()),
            "target_path": target_path,
            "ref_name": ref_name,
            "device": device,
            "max_new_tokens": max_new_tokens,
            "max_problems": args.max_problems,
            "n_samples": len(samples),
        },
        "defenses": {},
    }
    with (out / "w3_error_rows.jsonl").open("w", encoding="utf-8") as audit:
        for name, service in defenses.items():
            result = evaluate_defense(
                name, service, samples, args.timeout, args.batch_size, args.workers
            )
            for row in result.pop("rows"):
                audit.write(json.dumps(row, sort_keys=True) + "\n")
            summary["defenses"][name] = result
            (out / "w3_error_analysis_partial.json").write_text(
                json.dumps(summary, indent=2)
            )
            print(json.dumps({"defense": name, **result}, indent=2), flush=True)
    (out / "w3_error_analysis.json").write_text(json.dumps(summary, indent=2))
    md = [
        "# W3 Error Analysis",
        "",
        f"Generated: `{summary['metadata']['timestamp']}`",
        "",
        "| defense | pass@1 | refused | top failure |",
        "|---|---:|---:|---|",
    ]
    for name, row in summary["defenses"].items():
        top = row["top_errors"][0][0] if row["top_errors"] else "-"
        md.append(
            f"| {name} | {row['pass_at_1_pct']:.2f}% | {row['refusal_rate_pct']:.2f}% | `{top}` |"
        )
    (out / "w3_error_analysis.md").write_text("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
