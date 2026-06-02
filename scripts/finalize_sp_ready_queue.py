#!/usr/bin/env python3
"""Finalize prepared SP queue artifacts after queued evaluations finish."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "bin" / "python"


def run(cmd: list[str], log: Path) -> int:
    with log.open("a") as f:
        f.write(f"\n===== {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====\n")
        f.write(" ".join(cmd) + "\n")
        proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=f, stderr=subprocess.STDOUT)
        f.write(f"rc={proc.returncode}\n")
        return proc.returncode


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_final_report(output_dir: Path, w5_dir: Path, w3_dir: Path, summary_dir: Path) -> None:
    w5 = load_json(w5_dir / "w5" / "table6_paraphrase_robustness.json")
    w3 = load_json(w3_dir / "w3" / "w3_utility.json")
    lines = [
        "# SP Ready Queue Final Report",
        "",
        f"- timestamp: `{time.strftime('%Y-%m-%dT%H:%M:%S%z')}`",
        f"- hostname: `{socket.gethostname()}`",
        f"- python: `{platform.python_version()}`",
        "",
        "## New Completed Artifacts",
        "",
        f"- W5 B2/B3 gap: `{w5_dir}`",
        f"- W3 multilingual utility: `{w3_dir}`",
        f"- refreshed summary: `{summary_dir}`",
        "",
        "## New W5 B2/B3 Results",
        "",
    ]
    if isinstance(w5, dict):
        for name, row in w5.items():
            lines.append(
                f"- {name}: W4 {row.get('w4_summary', {}).get('rate_pct', '?')}%, "
                f"W5 {row.get('w5_summary', {}).get('rate_pct', '?')}%, "
                f"ratio {row.get('robustness_ratio', '?')}"
            )
    else:
        lines.append("- W5 result file not found.")
    lines += ["", "## New W3 Results", ""]
    if isinstance(w3, dict):
        for name, row in w3.items():
            lines.append(
                f"- {name}: pass@1 {row.get('pass_at_1', '?')}%, "
                f"correct {row.get('n_correct', '?')}/{row.get('n_problems', '?')}, "
                f"refusal {row.get('refusal_rate', '-')}"
            )
    else:
        lines.append("- W3 result file not found.")
    lines += [
        "",
        "## Still Blocked For Full PDF Claims",
        "",
        "- W2 LCCT full: missing real LCCT JSONL.",
        "- DP-SGD epsilon sweep: missing full training corpus and real per-epsilon DP checkpoints.",
        "- Multi-model full: missing real second-model config/checkpoint and full corpus.",
        "- Non-vacuous certificate calibration: current certificate remains vacuous and needs method/data improvement.",
    ]
    (output_dir / "final_report.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-dir", default="_run_results/sp_ready_queue_20260531_1730")
    parser.add_argument("--poll-sec", type=int, default=180)
    args = parser.parse_args()

    queue_dir = Path(args.queue_dir)
    log = queue_dir / "logs" / "finalizer.log"
    status = queue_dir / "finalizer_status.jsonl"
    w5_dir = REPO / "_run_results" / "w5_b2_b3_after_mps_free_20260531"
    w3_dir = REPO / "_run_results" / "w3_humanevalpack_multilingual_after_mps_free_20260531"
    w3_optimized_dir = REPO / "_run_results" / "w3_humanevalpack_multilingual_optimized_20260531"
    summary_dir = REPO / "_run_results" / "sp_evidence_summary_after_ready_queue_20260531"
    w5_required = w5_dir / "w5" / "table6_paraphrase_robustness.json"
    w3_candidates = [
        w3_optimized_dir / "w3" / "w3_utility.json",
        w3_dir / "w3" / "w3_utility.json",
    ]
    while True:
        selected_w3 = next((path for path in w3_candidates if path.exists()), None)
        ready = w5_required.exists() and selected_w3 is not None
        status.open("a").write(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "ready": ready,
            "selected_w3": str(selected_w3) if selected_w3 else None,
            "waiting_for": []
            if ready
            else [str(w5_required)] * (not w5_required.exists()) + ["one of: " + ", ".join(map(str, w3_candidates))] * (selected_w3 is None),
        }) + "\n")
        if ready:
            w3_dir = selected_w3.parents[1]
            break
        time.sleep(args.poll_sec)

    for run_dir in (w5_dir, w3_dir, summary_dir):
        if run_dir.exists():
            run([str(PYTHON), "scripts/write_run_manifest.py", str(run_dir)], log)
    write_final_report(queue_dir, w5_dir, w3_dir, summary_dir)
    run([str(PYTHON), "scripts/write_run_manifest.py", str(queue_dir)], log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
