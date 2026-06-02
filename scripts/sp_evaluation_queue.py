#!/usr/bin/env python3
"""SP evaluation queue runner.

The runner is intentionally conservative. It does not kill processes and it
does not launch another model job while the replicate post-gate job is queued
or running. It waits for the queued robustness run, then performs CPU/light-IO
finalization steps: evaluate summaries, manifests, paper tables, and a local
reproducibility patch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from safe_real_pilot import PYTHON, REPO, write_manifest


MAIN_RUN = REPO / "_run_results" / "safe_real_suite_positive_control_stable_20260528_190051"
REPLICATE_RUN = REPO / "_run_results" / "safe_real_suite_positive_control_stable_20260528_220342"
LOG_DIR = REPO / "_run_logs"


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=check)


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def post_gate_done(run_dir: Path) -> bool:
    summary = load_json(run_dir / "post_gate_heavy_summary.json")
    return isinstance(summary, dict) and summary.get("status") == "completed"


def eval_run(run_dir: Path) -> dict[str, Any]:
    result = run([str(PYTHON), "scripts/evaluate_run.py", "--run-dir", str(run_dir)])
    write_manifest(run_dir)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def rate(row: dict[str, Any] | None) -> str:
    if not row:
        return "-"
    if "rate_pct" in row:
        return f"{row['rate_pct']:.2f}%"
    if "rate" in row:
        return f"{100 * row['rate']:.2f}%"
    return "-"


def table_rows(run_dir: Path) -> dict[str, Any]:
    return {
        "run_dir": str(run_dir),
        "w1": load_json(run_dir / "figure2_extraction_vs_budget.json") or [],
        "direct": load_json(run_dir / "direct_canary_probe.json") or {},
        "w4": load_json(run_dir / "w4" / "table2_extraction.json") or {},
        "w5": load_json(run_dir / "w5" / "table6_paraphrase_robustness.json") or {},
        "post_gate": load_json(run_dir / "post_gate_heavy_summary.json") or {},
    }


def write_paper_tables(main: Path, replicate: Path, out_json: Path, out_md: Path) -> None:
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "main": table_rows(main),
        "replicate": table_rows(replicate),
    }
    out_json.write_text(json.dumps(data, indent=2))

    lines = [
        "# SP Evaluation Tables",
        "",
        f"- generated: {data['timestamp']}",
        f"- main_run: `{main}`",
        f"- replicate_run: `{replicate}`",
        "",
        "## W1 Extraction",
        "",
        "| run | B | extraction_rate |",
        "| --- | ---: | ---: |",
    ]
    for name in ("main", "replicate"):
        for row in data[name]["w1"]:
            lines.append(f"| {name} | {row.get('B')} | {100 * row.get('extraction_rate', 0):.2f}% |")

    lines.extend([
        "",
        "## Direct Probe",
        "",
        "| run | hits | total | rate |",
        "| --- | ---: | ---: | ---: |",
    ])
    for name in ("main", "replicate"):
        overall = data[name]["direct"].get("overall", {})
        lines.append(
            f"| {name} | {overall.get('n_success', '-')} | "
            f"{overall.get('n_total', '-')} | {overall.get('rate_pct', '-')}% |"
        )

    lines.extend([
        "",
        "## W4 Adaptive",
        "",
        "| run | defense | W4 workload | B=25 | B=50 | B=100 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for name in ("main", "replicate"):
        for defense, row in sorted(data[name]["w4"].items()):
            adaptive = row.get("A_adaptive", {})
            lines.append(
                f"| {name} | {defense} | {rate(row.get('W4_workload'))} | "
                f"{rate(adaptive.get('B=25'))} | {rate(adaptive.get('B=50'))} | {rate(adaptive.get('B=100'))} |"
            )

    lines.extend([
        "",
        "## W5 Paraphrase",
        "",
        "| run | defense | W4 rate | W5 rate | ratio |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for name in ("main", "replicate"):
        for defense, row in sorted(data[name]["w5"].items()):
            lines.append(
                f"| {name} | {defense} | {row.get('w4_rate', '-')}% | "
                f"{row.get('w5_rate', '-')}% | {row.get('ratio', '-')}x |"
            )

    out_md.write_text("\n".join(lines))


def write_repro_patch(path: Path) -> None:
    diff = run(["git", "diff"]).stdout
    status = run(["git", "status", "--short", "--branch"]).stdout
    path.write_text(f"# git status\n{status}\n\n# git diff\n{diff}")


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SP evaluation finalization queue.")
    parser.add_argument("--poll-sec", type=int, default=60)
    parser.add_argument("--once", action="store_true", help="Run ready steps once and exit if blocked.")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    status_path = LOG_DIR / "sp_evaluation_queue_status.json"
    queue_md = LOG_DIR / f"sp_evaluation_queue_{stamp}.md"
    queue_json = LOG_DIR / f"sp_evaluation_queue_{stamp}.json"

    queue = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "main_run": str(MAIN_RUN),
        "replicate_run": str(REPLICATE_RUN),
        "steps": [
            {"id": "main_post_gate", "status": "completed" if post_gate_done(MAIN_RUN) else "pending"},
            {"id": "replicate_post_gate", "status": "completed" if post_gate_done(REPLICATE_RUN) else "pending"},
            {"id": "evaluate_runs", "status": "pending"},
            {"id": "paper_tables", "status": "pending"},
            {"id": "manifest_repro_patch", "status": "pending"},
            {
                "id": "manual_audit_sample",
                "status": "queued_after_replicate",
                "notes": "Generate or sample 50-100 W4/W5 completions for exact/partial/no-leak labeling.",
            },
        ],
    }
    queue_json.write_text(json.dumps(queue, indent=2))
    queue_md.write_text(
        "\n".join([
            "# SP Evaluation Queue",
            "",
            f"- created_at: {queue['created_at']}",
            f"- main_run: `{MAIN_RUN}`",
            f"- replicate_run: `{REPLICATE_RUN}`",
            "",
            "| step | status |",
            "| --- | --- |",
            *[f"| {step['id']} | {step['status']} |" for step in queue["steps"]],
        ])
    )

    while True:
        status: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "queue_json": str(queue_json),
            "queue_md": str(queue_md),
            "main_post_gate_done": post_gate_done(MAIN_RUN),
            "replicate_post_gate_done": post_gate_done(REPLICATE_RUN),
            "steps": {},
        }
        if not status["main_post_gate_done"]:
            write_status(status_path, status | {"blocked_on": "main_post_gate"})
            if args.once:
                return 75
            time.sleep(args.poll_sec)
            continue
        if not status["replicate_post_gate_done"]:
            write_status(status_path, status | {"blocked_on": "replicate_post_gate"})
            if args.once:
                return 75
            time.sleep(args.poll_sec)
            continue

        status["steps"]["evaluate_main"] = eval_run(MAIN_RUN)
        status["steps"]["evaluate_replicate"] = eval_run(REPLICATE_RUN)
        write_paper_tables(
            MAIN_RUN,
            REPLICATE_RUN,
            LOG_DIR / "sp_paper_tables.json",
            LOG_DIR / "sp_paper_tables.md",
        )
        write_repro_patch(LOG_DIR / "sp_reproducibility_patch.diff")
        status["steps"]["paper_tables"] = {
            "json": str(LOG_DIR / "sp_paper_tables.json"),
            "markdown": str(LOG_DIR / "sp_paper_tables.md"),
        }
        status["steps"]["repro_patch"] = str(LOG_DIR / "sp_reproducibility_patch.diff")
        status["status"] = "completed"
        write_status(status_path, status)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
