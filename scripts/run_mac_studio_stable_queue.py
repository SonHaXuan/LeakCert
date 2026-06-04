#!/usr/bin/env python3
"""Run Mac-Studio-stable experiments sequentially with logs and checkpoints."""

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


def run(cmd: list[str], *, log_path: Path, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n=== COMMAND ===\n")
        log.write(" ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env={**os.environ, **(env or {})},
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return proc.wait()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def make_w5_config(base_cfg_path: Path, *, seed: int, out_dir: Path) -> Path:
    cfg = yaml.safe_load(base_cfg_path.read_text())
    cfg["seed"] = seed
    cfg["experiment_profile"] = f"mac_studio_stable_w5_learnedonly_seed{seed}"
    cfg["output_dir"] = str(out_dir)
    cfg.setdefault("canary", {})["seed"] = seed
    cfg.setdefault("canary", {})["n_eval_per_type"] = 8
    cfg.setdefault("model", {})["device"] = "mps"
    cfg.setdefault("model", {})["max_new_tokens"] = 16
    cfg.setdefault("evaluation", {})["batch_size"] = 32
    cfg.setdefault("evaluation", {})["query_budget"] = 200
    cfg.setdefault("evaluation", {})["run_defenses"] = ["B5", "LEAKCERT"]
    cfg.setdefault("runtime", {})["query_budget"] = 200
    cfg.setdefault("runtime", {})["refusal_threshold"] = 0.95
    cfg.setdefault("runtime", {})["use_learned_refusal"] = True
    cfg.setdefault("runtime", {})["use_refusal_heuristics"] = False
    cfg["notes"] = (
        "Mac Studio stable queue: learned-only threshold 0.95 W5 replication "
        "using existing Qwen positive-control checkpoint."
    )
    cfg_dir = out_dir / "configs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / f"w5_learnedonly_t095_seed{seed}.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def latest_entropy_audit_dir() -> Path | None:
    dirs = sorted(ROOT.glob("_run_results/entropy_cap_audit_*"), key=lambda p: p.stat().st_mtime)
    return dirs[-1] if dirs else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="")
    parser.add_argument("--seeds", default="44,45,46")
    parser.add_argument("--skip-w5", action="store_true")
    args = parser.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_root = ROOT / (args.output_root or f"_run_results/mac_studio_stable_queue_{ts}")
    logs = out_root / "logs"
    configs = out_root / "configs"
    out_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    configs.mkdir(parents=True, exist_ok=True)

    env = {
        "OMP_NUM_THREADS": "12",
        "MKL_NUM_THREADS": "12",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONUNBUFFERED": "1",
    }
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "queue": "mac_studio_stable",
        "seeds": [int(x) for x in args.seeds.split(",") if x.strip()],
        "output_root": str(out_root.relative_to(ROOT)),
    }
    write_json(out_root / "metadata.json", metadata)

    steps: list[dict[str, Any]] = []

    # P0/P1 posthoc: entropy audit and informative budget sweeps.
    audit_dir = out_root / "entropy_cap_audit"
    code = run(
        [
            sys.executable,
            "scripts/audit_entropy_caps.py",
            "--output-dir",
            str(audit_dir.relative_to(ROOT)),
        ],
        log_path=logs / "entropy_cap_audit.log",
        env=env,
    )
    steps.append({"step": "entropy_cap_audit", "returncode": code, "output": str(audit_dir.relative_to(ROOT))})

    kl_sources = {
        "certificate_refresh": "_run_results/certificate_refresh_20260531_2349/certificate/kl_estimates.json",
        "certificate_cpu_bounded": "_run_results/certificate_cpu_bounded_20260531_0344/certificate/kl_estimates.json",
        "safe_positive": "_run_results/safe_real_suite_positive_control_20260528_120114/certificate/kl_estimates.json",
        "safe_tiny": "_run_results/safe_real_suite_tiny_20260528_085312/certificate/kl_estimates.json",
    }
    for name, src in kl_sources.items():
        if not (ROOT / src).exists():
            continue
        sweep_out = out_root / "informative_budget" / name
        code = run(
            [
                sys.executable,
                "scripts/run_informative_budget_sweep.py",
                "--kl-estimates",
                src,
                "--output-dir",
                str(sweep_out.relative_to(ROOT)),
            ],
            log_path=logs / f"informative_budget_{name}.log",
            env=env,
        )
        steps.append({"step": f"informative_budget_{name}", "returncode": code, "output": str(sweep_out.relative_to(ROOT))})

    # MPS model workload: W5 learned-only t=0.95 replication for new seeds.
    if not args.skip_w5:
        base_cfg = ROOT / "_run_results/learnedonly_t095_validation_20260603_190245/configs/w5_seed42_t095.yaml"
        for seed in metadata["seeds"]:
            seed_out = out_root / f"w5_seed{seed}"
            cfg_path = make_w5_config(base_cfg, seed=seed, out_dir=seed_out)
            code = run(
                [sys.executable, "experiments/run_w5_paraphrase.py", "--config", str(cfg_path.relative_to(ROOT))],
                log_path=logs / f"w5_seed{seed}.log",
                env=env,
            )
            steps.append({"step": f"w5_seed{seed}", "returncode": code, "output": str(seed_out.relative_to(ROOT))})
            write_json(out_root / "queue_status.json", {"metadata": metadata, "steps": steps})
            if code != 0:
                break

    # Rebuild sanitized result package at the end; this will pick up the latest
    # standalone entropy/informative artifacts when available.
    code = run(
        [sys.executable, "scripts/build_updated_res_package.py"],
        log_path=logs / "build_updated_res_package.log",
        env=env,
    )
    steps.append({"step": "build_updated_res_package", "returncode": code, "output": "Updated-Res"})

    write_json(out_root / "queue_status.json", {"metadata": metadata, "steps": steps})
    print(json.dumps({"output_root": str(out_root.relative_to(ROOT)), "steps": steps}, indent=2))
    return 0 if all(step["returncode"] == 0 for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
