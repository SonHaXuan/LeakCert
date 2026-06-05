#!/usr/bin/env python3
"""Run extra reviewer-facing local replications at low resource risk.

This queue is intentionally smaller than the main Mac Studio stable queue. It
adds new W5 seeds and a compact component ablation while other CPU-heavy jobs
may be present on the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE_CFG = ROOT / "_run_results/learnedonly_t095_validation_20260603_190245/configs/w5_seed42_t095.yaml"


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def run_step(cmd: list[str], *, log_path: Path, env: dict[str, str]) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n=== COMMAND ===\n")
        log.write(" ".join(cmd) + "\n")
        log.write(f"started={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, **env},
            text=True,
        )
        code = proc.wait()
        log.write(f"\nfinished={time.strftime('%Y-%m-%dT%H:%M:%S%z')} returncode={code}\n")
        return code


def make_small_config(*, seed: int, out_dir: Path, n_eval_per_type: int, batch_size: int) -> Path:
    cfg = yaml.safe_load(BASE_CFG.read_text())
    cfg["seed"] = seed
    cfg["experiment_profile"] = f"reviewer_extra_light_seed{seed}"
    cfg["output_dir"] = str(out_dir)
    cfg.setdefault("canary", {})["seed"] = seed
    cfg["canary"]["n_eval_per_type"] = n_eval_per_type
    cfg["canary"]["n_eval"] = n_eval_per_type * 4
    cfg.setdefault("model", {})["device"] = "mps"
    cfg["model"]["max_new_tokens"] = 16
    cfg.setdefault("evaluation", {})["batch_size"] = batch_size
    cfg["evaluation"]["query_budget"] = 120
    cfg["evaluation"]["run_defenses"] = ["B5", "LEAKCERT"]
    cfg.setdefault("runtime", {})["query_budget"] = 120
    cfg["runtime"]["refusal_threshold"] = 0.95
    cfg["runtime"]["use_learned_refusal"] = True
    cfg["runtime"]["use_refusal_heuristics"] = False
    cfg["notes"] = (
        "Extra light reviewer-local replication. Small panel, B5 vs LEAKCERT, "
        "intended as sanity/replication evidence rather than full-scale claim."
    )
    cfg_dir = out_dir / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / f"w5_seed{seed}_small.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def read_w5_table(run_dir: Path) -> dict[str, Any]:
    table_path = run_dir / "w5" / "table6_paraphrase_robustness.json"
    if not table_path.exists():
        return {"status": "missing", "path": str(table_path.relative_to(ROOT))}
    table = json.loads(table_path.read_text())
    return {
        name: {
            "w4_rate_pct": row.get("w4_rate"),
            "w5_rate_pct": row.get("w5_rate"),
            "ratio": row.get("ratio"),
            "w4_n": row.get("w4_summary", {}).get("n_total"),
            "w5_n": row.get("w5_summary", {}).get("n_total"),
        }
        for name, row in table.items()
    }


def summarize_ablation(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "component_ablation_summary.json"
    if not path.exists():
        return {"status": "missing", "path": str(path.relative_to(ROOT))}
    data = json.loads(path.read_text())
    out = {}
    for name, row in data.get("results", {}).items():
        out[name] = {
            "W4_extraction_pct": row.get("W4", {}).get("extraction", {}).get("rate_pct"),
            "W5_extraction_pct": row.get("W5", {}).get("extraction", {}).get("rate_pct"),
            "W5_blocked_replaced_pct": row.get("W5", {}).get("refusal", {}).get("rate_pct"),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="")
    parser.add_argument("--seeds", default="47,48")
    parser.add_argument("--n-eval-per-type", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_root = ROOT / (args.output_root or f"_run_results/reviewer_local_extra_light_{ts}")
    logs = out_root / "logs"
    out_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    env = {
        "OMP_NUM_THREADS": str(args.threads),
        "MKL_NUM_THREADS": str(args.threads),
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONUNBUFFERED": "1",
    }
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "seeds": [int(x) for x in args.seeds.split(",") if x.strip()],
        "n_eval_per_type": args.n_eval_per_type,
        "batch_size": args.batch_size,
        "threads": args.threads,
        "base_config": str(BASE_CFG.relative_to(ROOT)),
        "output_root": str(out_root.relative_to(ROOT)),
    }
    write_json(out_root / "metadata.json", metadata)

    steps: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"metadata": metadata, "w5_replications": {}, "component_ablation": {}}

    for seed in metadata["seeds"]:
        run_dir = out_root / f"w5_seed{seed}"
        cfg = make_small_config(
            seed=seed,
            out_dir=run_dir,
            n_eval_per_type=args.n_eval_per_type,
            batch_size=args.batch_size,
        )
        code = run_step(
            [sys.executable, "experiments/run_w5_paraphrase.py", "--config", str(cfg.relative_to(ROOT))],
            log_path=logs / f"w5_seed{seed}.log",
            env=env,
        )
        steps.append({"step": f"w5_seed{seed}", "returncode": code, "output": str(run_dir.relative_to(ROOT))})
        summary["w5_replications"][str(seed)] = read_w5_table(run_dir)
        write_json(out_root / "queue_status.json", {"metadata": metadata, "steps": steps})
        write_json(out_root / "summary.json", summary)
        if code != 0:
            break

    # Compact component ablation using the first seed config. The ablation
    # script reads n_eval_per_type from the config, so this stays small.
    if all(step["returncode"] == 0 for step in steps):
        ablation_dir = out_root / "component_ablation_small"
        first_cfg = out_root / f"w5_seed{metadata['seeds'][0]}" / "configs" / f"w5_seed{metadata['seeds'][0]}_small.yaml"
        code = run_step(
            [
                sys.executable,
                "scripts/run_leakcert_component_ablation.py",
                "--config",
                str(first_cfg.relative_to(ROOT)),
                "--output-dir",
                str(ablation_dir.relative_to(ROOT)),
                "--batch-size",
                str(args.batch_size),
            ],
            log_path=logs / "component_ablation_small.log",
            env=env,
        )
        steps.append({"step": "component_ablation_small", "returncode": code, "output": str(ablation_dir.relative_to(ROOT))})
        summary["component_ablation"] = summarize_ablation(ablation_dir)

    write_json(out_root / "queue_status.json", {"metadata": metadata, "steps": steps})
    write_json(out_root / "summary.json", summary)
    md = [
        "# Reviewer Local Extra Light Results",
        "",
        f"- output: `{out_root.relative_to(ROOT)}`",
        f"- seeds: `{metadata['seeds']}`",
        f"- n_eval_per_type: `{args.n_eval_per_type}`",
        "",
        "## W5 Replications",
        "",
    ]
    for seed, rows in summary["w5_replications"].items():
        md.append(f"### Seed {seed}")
        if isinstance(rows, dict):
            for name, row in rows.items():
                if isinstance(row, dict):
                    md.append(
                        f"- {name}: W4 `{row.get('w4_rate_pct')}`%, "
                        f"W5 `{row.get('w5_rate_pct')}`%, ratio `{row.get('ratio')}`"
                    )
        md.append("")
    md.extend(["## Component Ablation", ""])
    for name, row in summary.get("component_ablation", {}).items():
        if isinstance(row, dict):
            md.append(
                f"- {name}: W4 `{row.get('W4_extraction_pct')}`%, "
                f"W5 `{row.get('W5_extraction_pct')}`%, "
                f"W5 blocked/replaced `{row.get('W5_blocked_replaced_pct')}`%"
            )
    (out_root / "summary.md").write_text("\n".join(md) + "\n")

    print(json.dumps({"output_root": str(out_root.relative_to(ROOT)), "steps": steps}, indent=2))
    return 0 if all(step["returncode"] == 0 for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
