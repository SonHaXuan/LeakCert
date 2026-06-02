#!/usr/bin/env python3
"""Live status monitor for post-gate W4/W5 runs.

This is intentionally read-only for model processes. It parses existing logs
and writes lightweight JSON/Markdown status files that can be used for audit
while long evaluations are still running.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]

PATH_A_RE = re.compile(r"\s+(?P<defense>\S+)\s+W4 rate = (?P<rate>[0-9.]+)% \((?P<hits>\d+)/(?P<total>\d+)\)")
ADAPTIVE_START_RE = re.compile(r"W4 \| B=\s*(?P<budget>\d+) \| (?P<defense>.+)$")
RATE_RE = re.compile(r"extraction rate = (?P<rate>[0-9.]+)%")


def run_text(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False).stdout.strip()


def parse_w4_log(path: Path) -> dict[str, Any]:
    path_a: dict[str, Any] = {}
    adaptive: dict[str, dict[str, Any]] = {}
    current: tuple[str, str] | None = None
    last_event = ""
    if not path.exists():
        return {"path_a": path_a, "adaptive": adaptive, "last_event": "w4_log_missing"}

    for line in path.read_text(errors="replace").splitlines():
        if "INFO]" in line:
            last_event = line
        m = PATH_A_RE.search(line)
        if m:
            defense = m.group("defense")
            path_a[defense] = {
                "rate_pct": float(m.group("rate")),
                "n_success": int(m.group("hits")),
                "n_total": int(m.group("total")),
            }
            continue
        m = ADAPTIVE_START_RE.search(line)
        if m:
            current = (f"B={int(m.group('budget'))}", m.group("defense").strip())
            adaptive.setdefault(current[1], {})
            continue
        m = RATE_RE.search(line)
        if m and current:
            budget, defense = current
            adaptive.setdefault(defense, {})[budget] = {"rate_pct": float(m.group("rate"))}
            current = None

    pending = None
    if current:
        budget, defense = current
        pending = {"budget": budget, "defense": defense}
    return {"path_a": path_a, "adaptive": adaptive, "pending": pending, "last_event": last_event}


def parse_w5_log(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "not_started"}
    lines = path.read_text(errors="replace").splitlines()
    status = "running"
    if any("Table 6" in line or "Saved" in line for line in lines[-80:]):
        status = "possibly_completed"
    return {"status": status, "last_lines": lines[-20:]}


def process_snapshot() -> list[dict[str, Any]]:
    out = run_text([
        "ps",
        "-o",
        "pid,ppid,etime,pcpu,pmem,rss,nice,command",
        "-ax",
    ])
    rows = []
    markers = ("run_w4_code_secret.py", "run_w5_paraphrase.py", "queue_post_gate_heavy.py")
    for line in out.splitlines()[1:]:
        if not any(marker in line for marker in markers):
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        rows.append({
            "pid": parts[0],
            "ppid": parts[1],
            "elapsed": parts[2],
            "pcpu": parts[3],
            "pmem": parts[4],
            "rss_kb": parts[5],
            "nice": parts[6],
            "command": parts[7],
        })
    return rows


def vm_free_gib() -> float | None:
    out = run_text(["vm_stat"])
    page_size = 16_384
    values: dict[str, int] = {}
    for line in out.splitlines():
        if "page size of" in line:
            page_size = int(line.split("page size of", 1)[1].split("bytes")[0].strip())
        elif ":" in line:
            key, raw = line.split(":", 1)
            digits = "".join(ch for ch in raw if ch.isdigit())
            if digits:
                values[key.strip()] = int(digits)
    pages = values.get("Pages free", 0) + values.get("Pages speculative", 0)
    return round(pages * page_size / (1024**3), 3)


def write_markdown(status: dict[str, Any], path: Path) -> None:
    w4 = status["w4"]
    lines = [
        f"# Post-gate live status",
        "",
        f"- timestamp: {status['timestamp']}",
        f"- run_dir: {status['run_dir']}",
        f"- free_gib: {status['free_gib']}",
        f"- w5_status: {status['w5']['status']}",
        f"- w4_pending: {w4.get('pending')}",
        "",
        "## W4 Path A",
        "",
    ]
    for defense, row in sorted(w4["path_a"].items()):
        lines.append(f"- {defense}: {row['rate_pct']}% ({row['n_success']}/{row['n_total']})")
    lines.extend(["", "## W4 Adaptive", ""])
    for defense, budgets in sorted(w4["adaptive"].items()):
        parts = [f"{budget}: {row['rate_pct']}%" for budget, row in sorted(budgets.items())]
        lines.append(f"- {defense}: {', '.join(parts)}")
    lines.extend(["", "## Processes", "", "```json", json.dumps(status["processes"], indent=2), "```"])
    path.write_text("\n".join(lines))


def snapshot(run_dir: Path) -> dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_dir": str(run_dir),
        "free_gib": vm_free_gib(),
        "processes": process_snapshot(),
        "w4": parse_w4_log(run_dir / "post_gate_w4_code_secret.log"),
        "w5": parse_w5_log(run_dir / "post_gate_w5_paraphrase.log"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write live post-gate W4/W5 status.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--poll-sec", type=int, default=0, help="0 writes one snapshot and exits.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    json_path = run_dir / "post_gate_live_status.json"
    md_path = run_dir / "post_gate_live_status.md"
    log_path = REPO / "_run_logs" / f"post_gate_live_monitor_{run_dir.name}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        status = snapshot(run_dir)
        json_path.write_text(json.dumps(status, indent=2))
        write_markdown(status, md_path)
        with log_path.open("a") as f:
            f.write(json.dumps(status) + "\n")
        print(json.dumps({"status": "written", "run_dir": str(run_dir), "log": str(log_path)}, indent=2))
        if args.poll_sec <= 0:
            return 0
        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
