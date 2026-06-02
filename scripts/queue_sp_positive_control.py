#!/usr/bin/env python3
"""Queue the SP positive-control run and post-process it when complete."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from safe_real_pilot import REPO, PYTHON, conflict_processes, memory_free_gib, vm_stat


def existing_completed_run(profile: str, model_id: str) -> Path | None:
    """Return the newest completed run for this profile/model, if present."""
    prefix = f"safe_real_suite_{profile}_"
    candidates = sorted((REPO / "_run_results").glob(f"{prefix}*"), reverse=True)
    for run_dir in candidates:
        metadata_path = run_dir / "metadata.json"
        summary_path = run_dir / "suite_summary.json"
        if not metadata_path.exists() or not summary_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
            summary = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            continue
        if metadata.get("model_id") != model_id:
            continue
        if summary.get("status") == "completed":
            return run_dir
    return None


def extract_run_dir(output: str) -> Path | None:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith(str(REPO / "_run_results")):
            return Path(stripped)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    run_dir = payload.get("run_dir") if isinstance(payload, dict) else None
    return Path(run_dir) if run_dir else None


def run_postprocess(run_dir: Path, poll_sec: int) -> None:
    subprocess.run(
        [str(PYTHON), "scripts/evaluate_run.py", "--run-dir", str(run_dir)],
        cwd=REPO,
        check=False,
    )
    subprocess.run(
        [
            str(PYTHON),
            "scripts/monitor_run_and_backup.py",
            "--run-dir",
            str(run_dir),
            "--poll-sec",
            str(poll_sec),
        ],
        cwd=REPO,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SP positive-control when resources are clear.")
    parser.add_argument("--poll-sec", type=int, default=30)
    parser.add_argument("--min-free-gib", type=float, default=96.0)
    parser.add_argument("--model-id", default="hf-internal-testing/tiny-random-gpt2")
    parser.add_argument("--profile", default="positive_control")
    parser.add_argument("--max-wait-sec", type=int, default=0, help="0 means wait indefinitely.")
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
                f"model_id={args.model_id}: {existing}; exiting queue",
                flush=True,
            )
            return 0

        conflicts = conflict_processes()
        free_gib = memory_free_gib(vm_stat())
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(
            f"{now} attempt={attempt} profile={args.profile} "
            f"conflicts={len(conflicts)} free_gib={free_gib:.2f} "
            f"min_free_gib={args.min_free_gib:.2f}",
            flush=True,
        )
        if conflicts:
            for line in conflicts[:4]:
                print(f"  conflict: {line[:240]}", flush=True)

        if not conflicts and free_gib >= args.min_free_gib:
            command = [
                str(PYTHON),
                "scripts/safe_real_pilot.py",
                "--profile",
                args.profile,
                "--model-id",
                args.model_id,
                "--min-free-gib",
                str(args.min_free_gib),
            ]
            print(f"{now} launching: {' '.join(command)}", flush=True)
            proc = subprocess.run(
                command,
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.stdout:
                print(proc.stdout, end="", flush=True)
            if proc.stderr:
                print(proc.stderr, end="", flush=True)

            run_dir = extract_run_dir(proc.stdout)
            if run_dir and run_dir.exists():
                print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} postprocess: {run_dir}", flush=True)
                run_postprocess(run_dir, args.poll_sec)

            if proc.returncode == 75:
                print("resource gate/lock blocked launch; continuing queue", flush=True)
                time.sleep(args.poll_sec)
                continue
            return proc.returncode

        if args.max_wait_sec and time.time() - started >= args.max_wait_sec:
            print(f"{now} max wait reached; exiting without launch", flush=True)
            return 75

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
