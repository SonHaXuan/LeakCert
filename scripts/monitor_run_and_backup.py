#!/usr/bin/env python3
"""Lightweight monitor for a LeakCert run directory.

The monitor is read-only while a run is active. When a suite completes, it
creates an audit report, manifest, and local tar.gz backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import tarfile
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / "_run_logs"
BACKUP_DIR = REPO / "_run_backups"
MPS_MARKERS = ("--device mps", "run_evaluation.py", "train_barrier.py")
LEAKCERT_MARKERS = (
    "run_w1_canary_finetune.py",
    "compute_certificate.py",
    "run_w4_code_secret.py",
    "run_w5_paraphrase.py",
    "safe_real_pilot.py",
)


def run_text(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    return result.stdout.strip()


def vm_stat() -> dict[str, int]:
    out = run_text(["vm_stat"])
    stats: dict[str, int] = {}
    page_size = 16_384
    for line in out.splitlines():
        if "page size of" in line:
            page_size = int(line.split("page size of", 1)[1].split("bytes")[0].strip())
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = "".join(ch for ch in raw if ch.isdigit())
        if value:
            stats[key.strip()] = int(value)
    stats["_page_size"] = page_size
    return stats


def free_gib() -> float:
    stats = vm_stat()
    pages = stats.get("Pages free", 0) + stats.get("Pages speculative", 0)
    return pages * stats.get("_page_size", 16_384) / (1024**3)


def process_lines() -> list[str]:
    ps = run_text(["ps", "aux"])
    current = str(os.getpid())
    lines = []
    for line in ps.splitlines():
        if current in line or "monitor_run_and_backup.py" in line:
            continue
        if any(marker in line for marker in (*MPS_MARKERS, *LEAKCERT_MARKERS)):
            lines.append(line)
    return lines


def current_stage(run_dir: Path) -> str:
    if (run_dir / "suite_summary.json").exists():
        return "suite_finished"
    for name in ("w5_paraphrase", "w4_code_secret", "certificate", "w1_canary_finetune"):
        log_path = run_dir / f"{name}.log"
        if log_path.exists():
            return name
    return "initializing"


def tail_lines(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(errors="replace").splitlines()
    return lines[-limit:]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(run_dir: Path) -> Path:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({
                "path": str(path.relative_to(run_dir)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    manifest = run_dir / "manifest.json"
    manifest.write_text(json.dumps(files, indent=2))
    return manifest


def write_report(run_dir: Path, status: dict, backup_path: Path | None) -> Path:
    lines = [
        f"# LeakCert Run Report: {run_dir.name}",
        "",
        f"- timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"- hostname: {socket.gethostname()}",
        f"- platform: {platform.platform()}",
        f"- run_dir: {run_dir}",
        f"- status: {status.get('status', 'unknown')}",
        f"- stage: {status.get('stage', 'unknown')}",
        f"- free_gib: {status.get('free_gib', 'unknown')}",
        f"- backup: {backup_path if backup_path else 'not_created'}",
        "",
        "## Suite Summary",
        "",
    ]
    summary_path = run_dir / "suite_summary.json"
    if summary_path.exists():
        lines.append("```json")
        lines.append(summary_path.read_text(errors="replace"))
        lines.append("```")
    else:
        lines.append("No suite_summary.json yet.")

    lines.extend(["", "## Recent Logs", ""])
    for name in ("w1_canary_finetune", "certificate", "w4_code_secret", "w5_paraphrase"):
        lines.append(f"### {name}")
        lines.append("```text")
        lines.extend(tail_lines(run_dir / f"{name}.log", 30))
        lines.append("```")
        lines.append("")

    report = run_dir / "run_report.md"
    report.write_text("\n".join(lines))
    return report


def backup_run(run_dir: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{run_dir.name}_{ts}.tar.gz"
    with tarfile.open(backup_path, "w:gz") as tar:
        tar.add(run_dir, arcname=run_dir.name)
    return backup_path


def status_snapshot(run_dir: Path) -> dict:
    lines = process_lines()
    leakcert = [line for line in lines if any(marker in line for marker in LEAKCERT_MARKERS)]
    mps = [line for line in lines if any(marker in line for marker in MPS_MARKERS)]
    external_mps = [line for line in mps if "LeakCert" not in line]
    summary_path = run_dir / "suite_summary.json"
    suite = json.loads(summary_path.read_text()) if summary_path.exists() else None
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_dir": str(run_dir),
        "stage": current_stage(run_dir),
        "status": suite.get("status") if suite else "running",
        "returncode": suite.get("returncode") if suite else None,
        "free_gib": round(free_gib(), 3),
        "leakcert_processes": leakcert,
        "external_mps_processes": external_mps,
        "warning": "external_mps_active" if external_mps else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor a LeakCert run and backup successful result.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--poll-sec", type=int, default=60)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    status_log = LOG_DIR / f"monitor_{run_dir.name}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    marker = run_dir / ".backup_complete"

    while True:
        status = status_snapshot(run_dir)
        with status_log.open("a") as f:
            f.write(json.dumps(status) + "\n")

        if status["status"] in {"completed", "failed", "blocked"}:
            backup_path = None
            write_manifest(run_dir)
            if status["status"] == "completed" and not marker.exists():
                backup_path = backup_run(run_dir)
                marker.write_text(str(backup_path) + "\n")
            elif marker.exists():
                backup_path = Path(marker.read_text().strip())
            write_report(run_dir, status, backup_path)
            print(json.dumps({"status": status["status"], "status_log": str(status_log)}, indent=2))
            return 0 if status["status"] == "completed" else 1

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
