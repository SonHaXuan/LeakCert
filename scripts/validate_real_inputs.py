#!/usr/bin/env python3
"""Validate real inputs before full-evaluation runs.

This is intentionally stricter than the experiment scripts. The experiments
may support synthetic fallbacks for local development, but this validator
marks those cases as blockers for paper evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import socket
import time
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
TODO_MARKER = "TODO_"


def resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def path_exists(value: str | None) -> bool:
    path = resolve_path(value)
    return bool(path and path.exists())


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and (
        TODO_MARKER in value or value.startswith("local-code-model-")
    )


def inspect_jsonl(path: Path, limit: int = 200) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "sampled_rows": 0,
                "sampled_limit": limit,
                "parse_errors": [{"line": 1, "error": str(exc)}],
                "keys": [],
                "categories": [],
                "missing_prompt": 0,
                "missing_secret_or_expected_secret": 0,
                "not_paper_grade_rows": 0,
            }
        if isinstance(obj, dict):
            rows_obj = (
                obj.get("data")
                or obj.get("examples")
                or obj.get("samples")
                or obj.get("items")
                or []
            )
        elif isinstance(obj, list):
            rows_obj = obj
        else:
            rows_obj = []
        return inspect_rows(rows_obj[:limit], limit)

    rows_obj = []
    parse_errors = []
    with path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if idx >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rows_obj.append(json.loads(line))
            except json.JSONDecodeError as exc:
                parse_errors.append({"line": idx + 1, "error": str(exc)})
    result = inspect_rows(rows_obj, limit)
    result["parse_errors"] = parse_errors[:10]
    return result


def inspect_rows(rows_obj: list[Any], limit: int) -> dict[str, Any]:
    rows = 0
    keys: set[str] = set()
    categories: set[str] = set()
    missing_prompt = 0
    missing_secret = 0
    not_paper_grade_rows = 0
    for obj in rows_obj:
        if not isinstance(obj, dict):
            continue
        rows += 1
        keys.update(obj.keys())
        if obj.get("not_paper_grade") or "NOT PAPER-GRADE" in str(obj):
            not_paper_grade_rows += 1
        if not obj.get("prompt"):
            missing_prompt += 1
        if not (obj.get("secret") or obj.get("expected_secret")):
            missing_secret += 1
        meta = obj.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("category"):
            categories.add(str(meta["category"]))
        if obj.get("category"):
            categories.add(str(obj["category"]))
    return {
        "sampled_rows": rows,
        "sampled_limit": limit,
        "parse_errors": [],
        "keys": sorted(keys),
        "categories": sorted(categories),
        "missing_prompt": missing_prompt,
        "missing_secret_or_expected_secret": missing_secret,
        "not_paper_grade_rows": not_paper_grade_rows,
    }


def checkpoint_status(path_value: str | None) -> dict[str, Any]:
    path = resolve_path(path_value)
    files = []
    if path and path.exists() and path.is_dir():
        for name in (
            "config.json",
            "model.safetensors",
            "pytorch_model.bin",
            "tokenizer.json",
        ):
            if (path / name).exists():
                files.append(name)
    return {
        "path": path_value,
        "exists": bool(path and path.exists()),
        "is_placeholder": is_placeholder(path_value),
        "recognized_files": files,
    }


def validate(cfg: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    corpus = cfg.get("corpus", {})
    model = cfg.get("model", {})
    finetune = cfg.get("finetune", {})
    finetune_mid = cfg.get("finetune_mid", {})
    finetune_dp = cfg.get("finetune_dp", {})
    evaluation = cfg.get("evaluation", {})
    canary = cfg.get("canary", {})

    lcct_path = resolve_path(corpus.get("lcct_path"))
    lcct = {
        "path": corpus.get("lcct_path"),
        "exists": bool(lcct_path and lcct_path.exists()),
        "inspection": None,
    }
    if lcct["exists"] and lcct_path:
        lcct["inspection"] = inspect_jsonl(lcct_path)
        insp = lcct["inspection"]
        if insp["parse_errors"]:
            blockers.append("LCCT JSONL has parse errors.")
        if insp["missing_prompt"]:
            blockers.append("LCCT JSONL has rows without prompt.")
        if insp["missing_secret_or_expected_secret"]:
            blockers.append("LCCT JSONL has rows without secret/expected_secret.")
        if insp.get("not_paper_grade_rows"):
            blockers.append("LCCT input contains NOT PAPER-GRADE/template rows.")
        if not insp["categories"]:
            warnings.append("LCCT JSONL has no category metadata in sampled rows.")
        if insp["sampled_rows"] < 200:
            warnings.append(
                "LCCT smoke file has fewer than 200 sampled rows; full W2 expects the real 4,832-item benchmark."
            )
    else:
        blockers.append("Missing real corpus.lcct_path for W2 LCCT.")

    train_path = resolve_path(corpus.get("path"))
    training_corpus = {
        "path": corpus.get("path"),
        "exists": bool(train_path and train_path.exists()),
        "inspection": None,
    }
    if training_corpus["exists"] and train_path and train_path.suffix == ".jsonl":
        training_corpus["inspection"] = inspect_jsonl(train_path, limit=50)
    else:
        blockers.append("Missing real corpus.path for W1/DP/multi-model training.")

    models = {
        "small_base": {
            "value": model.get("target_model_small") or model.get("target_model"),
            "is_placeholder": is_placeholder(
                model.get("target_model_small") or model.get("target_model")
            ),
        },
        "mid_base": {
            "value": model.get("target_model_mid"),
            "is_placeholder": is_placeholder(model.get("target_model_mid")),
        },
        "target_checkpoint": checkpoint_status(finetune.get("output_dir")),
        "mid_checkpoint": checkpoint_status(finetune_mid.get("output_dir")),
    }
    if models["small_base"]["is_placeholder"]:
        blockers.append("Small/base model ID is still a placeholder.")
    if models["mid_base"]["is_placeholder"]:
        blockers.append("Mid model ID is still a placeholder.")
    if not models["target_checkpoint"]["exists"]:
        warnings.append(
            "Small target checkpoint is absent; W1 must run before W2/W4/W5/certificate."
        )
    if not models["mid_checkpoint"]["exists"]:
        warnings.append(
            "Mid target checkpoint is absent; multi-model full needs W1 for the second model."
        )

    epsilons = [str(eps) for eps in evaluation.get("dp_epsilons", [1, 2, 4, 8, 16])]
    dp_checkpoints = {}
    configured_dp = finetune_dp.get("checkpoints", {})
    for eps in epsilons:
        status = checkpoint_status(configured_dp.get(eps))
        dp_accounting = False
        path = resolve_path(configured_dp.get(eps))
        if path and path.exists() and path.is_dir():
            dp_accounting = (path / "dp_accounting.json").exists()
        status["dp_accounting_exists"] = dp_accounting
        dp_checkpoints[eps] = status
        if not status["exists"]:
            blockers.append(f"Missing real DP checkpoint for epsilon={eps}.")
        elif not dp_accounting:
            blockers.append(f"Missing dp_accounting.json for epsilon={eps}.")

    k = int(canary.get("n_canaries", 0) or 0)
    budgets = cfg.get("certificate", {}).get("budgets", [])
    certificate = {
        "n_canaries": k,
        "log_k_nats": round(math.log(k), 4) if k > 0 else None,
        "budgets": budgets,
        "calibration_panel_sizes": cfg.get("certificate", {}).get(
            "calibration_panel_sizes", []
        ),
        "calibration_seeds": cfg.get("certificate", {}).get("calibration_seeds", []),
    }
    if k < 1000:
        warnings.append(
            "Certificate canary set is small for paper-scale non-vacuous calibration."
        )
    if not models["target_checkpoint"]["exists"]:
        blockers.append("Certificate calibration needs a real target checkpoint.")

    return {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
        },
        "lcct": lcct,
        "training_corpus": training_corpus,
        "models": models,
        "dp_checkpoints": dp_checkpoints,
        "certificate": certificate,
        "blockers": blockers,
        "warnings": warnings,
        "ready_for_full": not blockers,
        "smoke_sequence": [
            "W2 real LCCT smoke: 100 real prompts with require_real_lcct=true.",
            "DP-SGD smoke: epsilon=8 on a tiny real-corpus slice; verify dp_accounting.json and checkpoint reload.",
            "Multi-model smoke: second model W1/W4/W5 with n_eval_per_type=1-2.",
            "Certificate smoke: compute KL and certificate on the real checkpoint, then expand panel sizes/seeds.",
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Real-Input Validation",
        "",
        f"- timestamp: `{report['metadata']['timestamp']}`",
        f"- hostname: `{report['metadata']['hostname']}`",
        f"- ready_for_full: `{report['ready_for_full']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in report["blockers"]] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])
    lines.extend(["", "## Smoke Sequence", ""])
    lines.extend(
        [f"{idx}. {item}" for idx, item in enumerate(report["smoke_sequence"], 1)]
    )
    lines.extend(
        [
            "",
            "## Inputs",
            "",
            f"- LCCT: `{report['lcct']['path']}` exists={report['lcct']['exists']}",
            f"- training corpus: `{report['training_corpus']['path']}` exists={report['training_corpus']['exists']}",
            f"- small checkpoint: `{report['models']['target_checkpoint']['path']}` exists={report['models']['target_checkpoint']['exists']}",
            f"- mid checkpoint: `{report['models']['mid_checkpoint']['path']}` exists={report['models']['mid_checkpoint']['exists']}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    cfg_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(cfg_path.read_text())
    report = validate(cfg)
    report["metadata"]["config"] = str(cfg_path)
    (output_dir / "real_input_validation.json").write_text(json.dumps(report, indent=2))
    write_markdown(output_dir / "real_input_validation.md", report)
    return 0 if report["ready_for_full"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
