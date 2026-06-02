#!/usr/bin/env python3
"""Resource-gated queue for remaining SP full-evaluation work."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "bin" / "python"


def top_snapshot() -> str:
    proc = subprocess.run(
        ["top", "-l", "1", "-n", "0"],
        text=True,
        capture_output=True,
    )
    return proc.stdout


def cpu_idle_percent(snapshot: str) -> float | None:
    for line in snapshot.splitlines():
        if "CPU usage:" not in line:
            continue
        marker = "% idle"
        if marker not in line:
            return None
        before = line.split(marker)[0].split(",")[-1].strip()
        try:
            return float(before)
        except ValueError:
            return None
    return None


def mem_unused_gib(snapshot: str) -> float | None:
    for line in snapshot.splitlines():
        if "PhysMem:" not in line or "unused" not in line:
            continue
        token = line.split("unused")[0].split(",")[-1].strip()
        try:
            if token.endswith("G"):
                return float(token[:-1])
            if token.endswith("M"):
                return float(token[:-1]) / 1024.0
        except ValueError:
            return None
    return None


def memory_pressure_available_gib() -> float | None:
    """Estimate reclaimable memory on macOS from memory_pressure output.

    `top` reports only truly unused pages, which can stay near zero while the
    system is healthy because inactive/compressed pages are reclaimable. The
    `memory_pressure` free percentage is a better safety gate for this queue.
    """
    try:
        proc = subprocess.run(
            ["memory_pressure"],
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    pct = None
    for line in proc.stdout.splitlines():
        if "System-wide memory free percentage:" not in line:
            continue
        token = line.rsplit(":", 1)[-1].strip().rstrip("%")
        try:
            pct = float(token)
        except ValueError:
            pct = None
        break
    if pct is None:
        return None
    try:
        total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    return total / (1024.0 ** 3) * pct / 100.0


def active_heavy_processes() -> list[str]:
    proc = subprocess.run(["ps", "aux"], text=True, capture_output=True)
    needles = [
        "run_evaluation.py",
        "train_barrier",
        "scripts/reproduce.py",
        "run_repeated_w4_w5_evidence.py",
        "run_w1_canary_finetune.py",
        "run_w2_lcct.py",
        "run_w3_real_completion.py",
        "compute_certificate.py",
    ]
    rows = []
    for line in proc.stdout.splitlines():
        if "sp_full_eval_queue.py" in line:
            continue
        # Watchdog/screen wrappers may contain the heavy command names only as
        # search strings in their shell script. They should not block the queue.
        if "ds_watchdog" in line or "watchdog.log" in line:
            continue
        if "screen -ls" in line and "find outputs" in line:
            continue
        if any(needle in line for needle in needles):
            rows.append(line)
    return rows


def resources_ready(min_idle: float, min_mem_gib: float, require_no_heavy: bool) -> tuple[bool, dict]:
    snap = top_snapshot()
    idle = cpu_idle_percent(snap)
    mem_unused = mem_unused_gib(snap)
    mem_pressure_available = memory_pressure_available_gib()
    mem_candidates = [m for m in (mem_unused, mem_pressure_available) if m is not None]
    mem = max(mem_candidates) if mem_candidates else None
    heavy = active_heavy_processes()
    status = {
        "cpu_idle_pct": idle,
        "mem_unused_gib": mem_unused,
        "mem_pressure_available_gib": mem_pressure_available,
        "mem_gate_gib": mem,
        "heavy_processes": heavy[:20],
    }
    if idle is None or idle < min_idle:
        return False, status | {"reason": "cpu_busy"}
    if mem is None or mem < min_mem_gib:
        return False, status | {"reason": "memory_low"}
    if require_no_heavy and heavy:
        return False, status | {"reason": "heavy_process_exists"}
    return True, status | {"reason": "ready"}


def run_step(command: list[str], log_path: Path) -> int:
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "16",
        "MKL_NUM_THREADS": "16",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        "PYTHONUNBUFFERED": "1",
    })
    with log_path.open("a") as log:
        log.write(f"\n===== START {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
        log.write(" ".join(command) + "\n")
        proc = subprocess.run(command, cwd=REPO, env=env, text=True, stdout=log, stderr=subprocess.STDOUT)
        log.write(f"===== END rc={proc.returncode} {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-dir", required=True)
    parser.add_argument("--poll-sec", type=int, default=120)
    parser.add_argument("--min-cpu-idle-pct", type=float, default=50.0)
    parser.add_argument("--min-mem-gib", type=float, default=160.0)
    parser.add_argument("--require-no-heavy", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    queue_dir = Path(args.queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    status_path = queue_dir / "queue_status.jsonl"
    plan_path = queue_dir / "queue_plan.json"
    plan = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "policy": {
            "smoke_before_full": True,
            "do_not_use_synthetic_for_full_claims": True,
            "stop_on_preflight_blockers": True,
            "do_not_kill_processes": True,
        },
        "steps": [
            {
                "id": "preflight",
                "command": [
                    str(PYTHON),
                    "scripts/sp_full_eval_preflight.py",
                    "--config",
                    "experiments/configs/full_scale.yaml",
                    "--output-dir",
                    str(queue_dir / "preflight"),
                ],
                "log": str(queue_dir / "preflight.log"),
                "status": "pending",
            }
        ],
        "blocked_full_steps": [
            "W2 full waits for real LCCT JSONL.",
            "W3 full waits for utility dataset smoke/cache verification.",
            "DP sweep waits for real training corpus and DP checkpoint smoke.",
            "Multi-model waits for real model IDs/corpus and second-model smoke.",
            "Certificate calibration waits for preflight and a bounded E1 smoke.",
        ],
    }
    if not plan_path.exists():
        plan_path.write_text(json.dumps(plan, indent=2))

    while True:
        ready, resource_status = resources_ready(
            args.min_cpu_idle_pct,
            args.min_mem_gib,
            args.require_no_heavy,
        )
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "ready": ready,
            "resource_status": resource_status,
        }
        if not ready:
            status_path.open("a").write(json.dumps(event) + "\n")
            if args.once:
                return 75
            time.sleep(args.poll_sec)
            continue

        step = plan["steps"][0]
        rc = run_step(step["command"], Path(step["log"]))
        step["status"] = "completed" if rc == 0 else "failed"
        step["returncode"] = rc
        step["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        plan_path.write_text(json.dumps(plan, indent=2))
        status_path.open("a").write(json.dumps(event | {"step": step}) + "\n")
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
