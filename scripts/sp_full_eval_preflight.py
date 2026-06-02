#!/usr/bin/env python3
"""Preflight the remaining SP full-evaluation items before queuing heavy runs."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]


def exists(path: str | None) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def run(cmd: list[str]) -> dict:
    started = time.time()
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "duration_sec": round(time.time() - started, 3),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def dataset_status(cfg: dict) -> dict:
    corpus = cfg.get("corpus", {})
    return {
        "training_corpus": {
            "path": corpus.get("path"),
            "exists": exists(corpus.get("path")),
            "required_for": ["multi-model full", "DP-SGD full"],
        },
        "lcct": {
            "path": corpus.get("lcct_path"),
            "exists": exists(corpus.get("lcct_path")),
            "required_for": ["W2 full"],
            "note": "If absent, W2LCCT falls back to synthetic prompts; do not use that as full LCCT evidence.",
        },
        "utility_eval": {
            "path": corpus.get("utility_eval_path"),
            "exists": exists(corpus.get("utility_eval_path")),
            "required_for": ["W3 local full"],
            "note": "If absent, W3 attempts datasets.load_dataset; smoke must verify dataset availability/cache.",
        },
    }


def model_status(cfg: dict) -> dict:
    model_cfg = cfg.get("model", {})
    ft = cfg.get("finetune", {})
    dp = cfg.get("finetune_dp", {})
    return {
        "target_checkpoint": {
            "path": ft.get("output_dir"),
            "exists": exists(ft.get("output_dir")),
        },
        "dp_checkpoint": {
            "path": dp.get("output_dir"),
            "exists": exists(dp.get("output_dir")),
        },
        "small_model_id": model_cfg.get("target_model_small") or model_cfg.get("target_model"),
        "mid_model_id": model_cfg.get("target_model_mid"),
        "full_config_note": "experiments/configs/full_scale.yaml uses local-code-model-* placeholders unless overridden.",
    }


def task_matrix(data: dict, models: dict) -> dict:
    return {
        "W2_full_LCCT": {
            "status": "blocked" if not data["lcct"]["exists"] else "needs_smoke",
            "blockers": [] if data["lcct"]["exists"] else ["missing real LCCT JSONL path in config"],
            "smoke_first": "Run W2 on 50 real LCCT prompts and verify expected_secret/category coverage.",
        },
        "W3_full_utility": {
            "status": "needs_smoke",
            "blockers": [],
            "smoke_first": "Load 10-20 utility_eval/code_eval samples, run B1/B5/LEAKCERT, verify evaluator and pass@1 are meaningful.",
        },
        "DP_sweep": {
            "status": "blocked" if not data["training_corpus"]["exists"] else "needs_smoke",
            "blockers": [] if data["training_corpus"]["exists"] else ["missing training corpus for DP fine-tuning"],
            "smoke_first": "Run DP-SGD on tiny corpus for eps=8, verify opacus path, dp_accounting.json, and checkpoint load.",
            "quality_note": "Current run_dp_sweep is analytic/clamped unless separate DP checkpoints are trained per epsilon.",
        },
        "multi_model": {
            "status": "blocked" if not data["training_corpus"]["exists"] else "needs_smoke",
            "blockers": [] if data["training_corpus"]["exists"] else ["missing full training corpus", "full config local-code-model-* placeholders need real model IDs"],
            "smoke_first": "Run second-model tiny W1/W4/W5 with n_eval_per_type=1-2 before full.",
        },
        "certificate_calibration": {
            "status": "needs_smoke" if models["target_checkpoint"]["exists"] else "blocked",
            "blockers": [] if models["target_checkpoint"]["exists"] else ["missing target checkpoint"],
            "smoke_first": "Run E1/certificate on panel sizes <= current panel first; full 500/1000/5000/|K| requires much larger panel.",
        },
    }


def write_md(path: Path, report: dict) -> None:
    lines = [
        "# SP Full Evaluation Preflight",
        "",
        f"- timestamp: `{report['metadata']['timestamp']}`",
        f"- hostname: `{report['metadata']['hostname']}`",
        f"- config: `{report['metadata']['config']}`",
        "",
        "## Task Status",
        "",
        "| task | status | blockers | smoke first |",
        "| --- | --- | --- | --- |",
    ]
    for task, row in report["tasks"].items():
        blockers = "; ".join(row.get("blockers", [])) or "-"
        lines.append(f"| {task} | {row['status']} | {blockers} | {row.get('smoke_first', '-')} |")
    lines.extend([
        "",
        "## Decision",
        "",
        report["decision"],
    ])
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="experiments/configs/full_scale.yaml")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--python", default=str(REPO / ".venv" / "bin" / "python"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    data = dataset_status(cfg)
    models = model_status(cfg)
    tasks = task_matrix(data, models)
    compile_checks = [
        run([args.python, "-m", "py_compile", "experiments/run_w2_lcct.py"]),
        run([args.python, "-m", "py_compile", "experiments/run_w3_real_completion.py"]),
        run([args.python, "-m", "py_compile", "experiments/compute_certificate.py"]),
        run([args.python, "-m", "py_compile", "experiments/run_w1_canary_finetune.py"]),
    ]
    imports_ok = run([
        args.python,
        "-c",
        "import opacus, datasets, torch; print('opacus/datasets/torch imports ok')",
    ])
    hard_blockers = [
        f"{task}: {', '.join(row.get('blockers', []))}"
        for task, row in tasks.items()
        if row["status"] == "blocked"
    ]
    decision = (
        "Do not launch full runs yet. Queue smoke/preflight gates first; full W2/DP/multi-model are blocked until real data/model inputs are provided."
        if hard_blockers
        else "Full runs may be queued after smoke gates pass."
    )
    report = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "config": str(cfg_path),
            "python_executable": args.python,
            "git_commit": run(["git", "rev-parse", "HEAD"]).get("stdout_tail", "").strip(),
            "screen": shutil.which("screen"),
        },
        "data": data,
        "models": models,
        "tasks": tasks,
        "compile_checks": compile_checks,
        "imports": imports_ok,
        "hard_blockers": hard_blockers,
        "decision": decision,
    }
    (output_dir / "preflight.json").write_text(json.dumps(report, indent=2))
    write_md(output_dir / "preflight.md", report)
    print(json.dumps({"output_dir": str(output_dir), "decision": decision, "hard_blockers": hard_blockers}, indent=2))
    return 0 if not any(c["returncode"] for c in compile_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
