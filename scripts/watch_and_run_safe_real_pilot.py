#!/usr/bin/env python3
"""Poll resources and launch the safe tiny W1 pilot once resources are clear."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from safe_real_pilot import REPO, PYTHON, conflict_processes, memory_free_gib, vm_stat


def existing_completed_run(profile: str, model_id: str) -> Path | None:
    prefix = f"safe_real_suite_{profile}_"
    for run_dir in sorted((REPO / "_run_results").glob(f"{prefix}*"), reverse=True):
        metadata_path = run_dir / "metadata.json"
        summary_path = run_dir / "suite_summary.json"
        if not metadata_path.exists() or not summary_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
            summary = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            continue
        if metadata.get("model_id") == model_id and summary.get("status") == "completed":
            return run_dir
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for resources, then run safe_real_pilot.py.")
    parser.add_argument("--poll-sec", type=int, default=60)
    parser.add_argument("--min-free-gib", type=float, default=64.0)
    parser.add_argument("--max-wait-sec", type=int, default=0, help="0 means wait indefinitely.")
    parser.add_argument("--profile", choices=["tiny", "positive_control", "positive_control_stable"], default="tiny")
    parser.add_argument("--model-id", default="hf-internal-testing/tiny-random-gpt2")
    args = parser.parse_args()

    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        existing = existing_completed_run(args.profile, args.model_id)
        if existing:
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            print(
                f"{now} completed run already exists for profile={args.profile} "
                f"model_id={args.model_id}: {existing}; exiting watcher",
                flush=True,
            )
            return 0

        conflicts = conflict_processes()
        free_gib = memory_free_gib(vm_stat())
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(
            f"{now} attempt={attempt} conflicts={len(conflicts)} "
            f"free_gib={free_gib:.2f} min_free_gib={args.min_free_gib:.2f}",
            flush=True,
        )
        if not conflicts and free_gib >= args.min_free_gib:
            command = [
                str(PYTHON),
                str(REPO / "scripts" / "safe_real_pilot.py"),
                "--min-free-gib",
                str(args.min_free_gib),
                "--profile",
                args.profile,
                "--model-id",
                args.model_id,
            ]
            print(f"{now} launching: {' '.join(command)}", flush=True)
            return subprocess.run(command, cwd=REPO).returncode

        if args.max_wait_sec and time.time() - started >= args.max_wait_sec:
            print(f"{now} max wait reached; exiting without launch", flush=True)
            return 75

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
