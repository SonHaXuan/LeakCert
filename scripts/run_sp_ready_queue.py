#!/usr/bin/env python3
"""Run a prepared SP queue only after resource gates are clear."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_THREADS = "32"


def run_text(cmd: list[str], timeout: int | None = None) -> str:
    try:
        return subprocess.run(
            cmd,
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=timeout,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def cpu_idle_pct() -> float | None:
    out = run_text(["top", "-l", "1", "-n", "0"], timeout=15)
    for line in out.splitlines():
        if "CPU usage:" not in line or "% idle" not in line:
            continue
        token = line.split("% idle")[0].split(",")[-1].strip()
        try:
            return float(token)
        except ValueError:
            return None
    return None


def memory_pressure_free_pct() -> float | None:
    out = run_text(["memory_pressure"], timeout=15)
    for line in out.splitlines():
        if "System-wide memory free percentage:" not in line:
            continue
        token = line.rsplit(":", 1)[-1].strip().rstrip("%")
        try:
            return float(token)
        except ValueError:
            return None
    return None


def active_heavy_processes(needles: list[str]) -> list[str]:
    out = run_text(["ps", "aux"], timeout=15)
    rows = []
    for line in out.splitlines():
        if "run_sp_ready_queue.py" in line:
            continue
        if "ds_watchdog" in line or "watchdog.log" in line:
            continue
        if any(needle in line for needle in needles):
            rows.append(line)
    return rows


def gate_status(plan: dict) -> tuple[bool, dict]:
    gate = plan["resource_gate"]
    idle = cpu_idle_pct()
    free_pct = memory_pressure_free_pct()
    heavy = active_heavy_processes(gate["must_have_no_active_heavy_process_matching"])
    status = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "cpu_idle_pct": idle,
        "memory_pressure_free_pct": free_pct,
        "heavy_processes": heavy[:20],
    }
    if heavy:
        return False, status | {"reason": "heavy_process_exists"}
    if idle is None or idle < float(gate["cpu_idle_pct_min_for_start"]):
        return False, status | {"reason": "cpu_busy"}
    if free_pct is None or free_pct < float(gate["memory_pressure_free_pct_min"]):
        return False, status | {"reason": "memory_pressure_high"}
    return True, status | {"reason": "ready"}


def run_step(step: dict, log_path: Path) -> int:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "OMP_NUM_THREADS": DEFAULT_THREADS,
            "MKL_NUM_THREADS": DEFAULT_THREADS,
            "VECLIB_MAXIMUM_THREADS": DEFAULT_THREADS,
            "NUMEXPR_NUM_THREADS": DEFAULT_THREADS,
            "TOKENIZERS_PARALLELISM": "false",
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        }
    )
    with log_path.open("a") as log:
        log.write(f"\n===== START {step['id']} {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
        log.write(step["command"] + "\n")
        proc = subprocess.run(
            step["command"],
            cwd=REPO,
            env=env,
            shell=True,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        log.write(f"===== END {step['id']} rc={proc.returncode} {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--poll-sec", type=int, default=180)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    queue_dir = plan_path.parent
    status_path = queue_dir / "runner_status.jsonl"
    log_dir = queue_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plan = json.loads(plan_path.read_text())
    for step in plan["ready_steps"]:
        if step.get("runner_status") == "completed":
            continue
        while True:
            ready, status = gate_status(plan)
            status_path.open("a").write(json.dumps(status | {"next_step": step["id"]}) + "\n")
            if ready:
                break
            if args.once:
                return 75
            time.sleep(args.poll_sec)
        rc = run_step(step, log_dir / f"{step['id']}.log")
        step["runner_status"] = "completed" if rc == 0 else "failed"
        step["returncode"] = rc
        step["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        plan_path.write_text(json.dumps(plan, indent=2))
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
