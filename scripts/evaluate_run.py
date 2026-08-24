#!/usr/bin/env python3
"""Summarize a completed LeakCert run into audit-friendly outputs."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def collect_rates(table: dict[str, Any] | None) -> dict[str, Any]:
    if not table:
        return {}
    result = {}
    for name, value in table.items():
        if isinstance(value, dict):
            row = {}
            for key in ("W4_workload", "A_adaptive"):
                if key in value:
                    row[key] = value[key]
            for key in ("w4_summary", "w5_summary", "ratio", "per_mode"):
                if key in value:
                    row[key] = value[key]
            result[name] = row or value
        else:
            result[name] = value
    return result


def summarize_run(run_dir: Path) -> dict[str, Any]:
    suite = load_json(run_dir / "suite_summary.json")
    w1_cert = load_json(run_dir / "table1_certificate_sweep.json")
    w1_extract = load_json(run_dir / "figure2_extraction_vs_budget.json")
    cert = load_json(run_dir / "certificate" / "table1_certificate.json")
    tightness = load_json(run_dir / "certificate" / "table3_tightness.json")
    w4 = load_json(run_dir / "w4" / "table2_extraction.json")
    w5 = load_json(run_dir / "w5" / "table6_paraphrase_robustness.json")

    steps = suite.get("steps", []) if isinstance(suite, dict) else []
    warnings: list[str] = []
    if not suite:
        warnings.append("suite_summary_missing")
    elif suite.get("status") != "completed":
        warnings.append(f"suite_status_{suite.get('status')}")
    if not w5:
        warnings.append("w5_results_missing")
    if not w4:
        warnings.append("w4_results_missing")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "run_dir": str(run_dir),
        "suite_status": suite.get("status") if isinstance(suite, dict) else "unknown",
        "returncode": suite.get("returncode") if isinstance(suite, dict) else None,
        "duration_sec": suite.get("duration_sec") if isinstance(suite, dict) else None,
        "steps": steps,
        "w1_certificate_sweep": w1_cert or [],
        "w1_extraction_vs_budget": w1_extract or [],
        "certificate_table1": cert or [],
        "certificate_tightness": tightness or [],
        "w4": collect_rates(w4),
        "w5": collect_rates(w5),
        "warnings": warnings,
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        f"# Evaluation Summary: {Path(summary['run_dir']).name}",
        "",
        f"- status: {summary['suite_status']}",
        f"- returncode: {summary['returncode']}",
        f"- duration_sec: {summary['duration_sec']}",
        f"- warnings: {', '.join(summary['warnings']) or 'none'}",
        "",
        "## Steps",
        "",
    ]
    for step in summary["steps"]:
        lines.append(
            f"- {step.get('name')}: {step.get('status')} "
            f"rc={step.get('returncode')} duration={step.get('duration_sec')}"
        )

    lines.extend(["", "## W1 Extraction", ""])
    for row in summary["w1_extraction_vs_budget"]:
        lines.append(
            f"- B={row.get('B')}: extraction_rate={row.get('extraction_rate')}"
        )

    lines.extend(["", "## W4", ""])
    if summary["w4"]:
        lines.append("```json")
        lines.append(json.dumps(summary["w4"], indent=2))
        lines.append("```")
    else:
        lines.append("No W4 table found.")

    lines.extend(["", "## W5", ""])
    if summary["w5"]:
        lines.append("```json")
        lines.append(json.dumps(summary["w5"], indent=2))
        lines.append("```")
    else:
        lines.append("No W5 table found.")

    lines.extend(["", "## Certificate Tightness", ""])
    for row in summary["certificate_tightness"]:
        lines.append(
            f"- B={row.get('B')}: cert={row.get('cert_nats')} "
            f"emp={row.get('emp_mi_nats')} ratio={row.get('ratio')}"
        )

    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a completed LeakCert run.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-sec", type=int, default=60)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    while args.wait and not (run_dir / "suite_summary.json").exists():
        time.sleep(args.poll_sec)

    summary = summarize_run(run_dir)
    (run_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2))
    write_markdown(summary, run_dir / "evaluation_summary.md")
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "status": summary["suite_status"],
                "warnings": summary["warnings"],
            },
            indent=2,
        )
    )
    return 0 if summary["suite_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
