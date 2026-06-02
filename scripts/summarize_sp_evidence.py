#!/usr/bin/env python3
"""Summarize current LeakCert evidence for SP submission planning."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import socket
import time
from collections import defaultdict
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def wilson(success: int, total: int) -> dict:
    if total <= 0:
        return {"rate": 0.0, "rate_pct": 0.0, "n_success": success, "n_total": total, "ci95_pct": [0.0, 0.0]}
    z = 1.959963984540054
    p = success / total
    denom = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4 * total)) / total) / denom
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return {
        "rate": p,
        "rate_pct": round(p * 100.0, 2),
        "n_success": success,
        "n_total": total,
        "ci95_pct": [round(lo * 100.0, 2), round(hi * 100.0, 2)],
    }


def add_ratio(row: dict, baseline: dict, method: dict) -> dict:
    base_rate = baseline.get("rate", 0.0)
    method_rate = method.get("rate", 0.0)
    row["absolute_reduction_pct"] = round((base_rate - method_rate) * 100.0, 2)
    row["relative_rate"] = round(method_rate / base_rate, 3) if base_rate > 0 else None
    row["relative_reduction_pct"] = round((1.0 - method_rate / base_rate) * 100.0, 2) if base_rate > 0 else None
    return row


def summarize_audit(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "path": str(path), "by_defense": [], "by_type_mode": []}
    groups = defaultdict(lambda: [0, 0])
    defenses = defaultdict(lambda: [0, 0])
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (
            row.get("defense"),
            row.get("workload"),
            row.get("canary_type") or "unknown",
            row.get("paraphrase_mode") or "direct",
        )
        groups[key][0] += int(bool(row.get("hit")))
        groups[key][1] += 1
        defenses[(row.get("defense"), row.get("workload"))][0] += int(bool(row.get("hit")))
        defenses[(row.get("defense"), row.get("workload"))][1] += 1

    by_type_mode = []
    for key, (hits, total) in sorted(groups.items()):
        defense, workload, canary_type, paraphrase_mode = key
        by_type_mode.append({
            "defense": defense,
            "workload": workload,
            "canary_type": canary_type,
            "paraphrase_mode": paraphrase_mode,
            **wilson(hits, total),
        })

    by_defense = []
    for key, (hits, total) in sorted(defenses.items()):
        defense, workload = key
        by_defense.append({"defense": defense, "workload": workload, **wilson(hits, total)})
    return {"by_defense": by_defense, "by_type_mode": by_type_mode}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(output_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file():
            rows.append({"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-run", required=True)
    parser.add_argument("--replicate-run", required=True)
    parser.add_argument("--phase-a-run", default=None)
    parser.add_argument("--phase-b-run", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    main_run = Path(args.main_run)
    replicate_run = Path(args.replicate_run)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = {"main": main_run, "replicate": replicate_run}
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "main_run": str(main_run.resolve()),
            "replicate_run": str(replicate_run.resolve()),
            "phase_a_run": str(Path(args.phase_a_run).resolve()) if args.phase_a_run else None,
            "phase_b_run": str(Path(args.phase_b_run).resolve()) if args.phase_b_run else None,
        },
        "w4": {},
        "w5": {},
        "audit": {},
        "phase_a": None,
        "phase_b": None,
        "coverage": {},
    }

    for label, run_dir in runs.items():
        w4 = load_json(run_dir / "w4" / "table2_extraction.json")
        w5 = load_json(run_dir / "w5" / "table6_paraphrase_robustness.json")
        summary["w4"][label] = w4
        summary["w5"][label] = w5
        summary["audit"][label] = summarize_audit(run_dir / "w5" / "audit_samples.jsonl")

    if args.phase_a_run:
        phase_dir = Path(args.phase_a_run)
        phase_summary = phase_dir / "phase_a_smoke_summary.json"
        if phase_summary.exists():
            summary["phase_a"] = load_json(phase_summary)
        else:
            summary["phase_a"] = {"status": "running_or_missing", "path": str(phase_summary)}

    if args.phase_b_run:
        phase_dir = Path(args.phase_b_run)
        phase_summary = phase_dir / "b2_b3_sweep_summary.json"
        partial_summary = phase_dir / "b2_b3_sweep_partial.json"
        if phase_summary.exists():
            summary["phase_b"] = load_json(phase_summary)
        elif partial_summary.exists():
            summary["phase_b"] = load_json(partial_summary)
        else:
            summary["phase_b"] = {"status": "running_or_missing", "path": str(phase_summary)}

    for label, w5 in summary["w5"].items():
        if "B1_no_defense" in w5 and "LEAKCERT" in w5:
            row = {
                "b1_w5_pct": w5["B1_no_defense"]["w5_summary"]["rate_pct"],
                "leakcert_w5_pct": w5["LEAKCERT"]["w5_summary"]["rate_pct"],
            }
            add_ratio(row, w5["B1_no_defense"]["w5_summary"], w5["LEAKCERT"]["w5_summary"])
            summary["coverage"][f"{label}_w5_b8_effect"] = row

    summary["coverage"]["pdf_claims"] = {
        "covered_small_scale": [
            "W1 canary fine-tuning main+replicate",
            "W4 extraction main+replicate",
            "W5 paraphrase/B8-style extraction main+replicate",
            "B1/B5/LEAKCERT comparison",
            "Wilson confidence intervals",
            "audit samples with prompts/completions/hits",
        ],
        "running_now": [
            "none",
        ],
        "completed_additional_smoke": [
            "B4 rate-limit smoke",
            "B7 Carlini smoke",
            "W3 utility/refusal/latency smoke",
            "B2 temperature sweep smoke",
            "B3 top-p sweep smoke",
        ],
        "not_yet_full_scale": [
            "W2 LCCT full benchmark",
            "full HumanEval-X/MBPP+",
            "DP-SGD epsilon sweep",
            "second large open-weight model",
            "full 7900/39500 prompt W4/W5 scale",
            "non-vacuous certificate calibration curves",
        ],
    }

    json_path = output_dir / "sp_evidence_summary.json"
    md_path = output_dir / "sp_evidence_summary.md"
    json_path.write_text(json.dumps(summary, indent=2))

    lines = [
        "# SP Evidence Summary",
        "",
        f"Generated: {summary['metadata']['timestamp']}",
        "",
        "## Strongest Current Signal",
    ]
    for label in ("main", "replicate"):
        effect = summary["coverage"][f"{label}_w5_b8_effect"]
        lines.append(
            f"- {label}: B1 W5 {effect['b1_w5_pct']:.2f}% vs LEAKCERT "
            f"{effect['leakcert_w5_pct']:.2f}% "
            f"(absolute reduction {effect['absolute_reduction_pct']:.2f} pp, "
            f"relative reduction {effect['relative_reduction_pct']:.2f}%)."
        )
    lines += [
        "",
        "## Phase A Status",
        f"- {summary['phase_a']['status'] if isinstance(summary['phase_a'], dict) and 'status' in summary['phase_a'] else 'completed'}",
        "",
        "## Phase B Decoding Sweep",
    ]
    if isinstance(summary["phase_b"], dict) and "b2_temperature" in summary["phase_b"]:
        for family, label_name in (("b2_temperature", "B2"), ("b3_top_p", "B3")):
            for name, value in summary["phase_b"].get(family, {}).items():
                lines.append(f"- {label_name} {name}: {value['summary']['rate_pct']:.2f}%")
    else:
        lines.append("- not available")
    lines += [
        "",
        "## Remaining Full-Scale Gaps",
    ]
    for item in summary["coverage"]["pdf_claims"]["not_yet_full_scale"]:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n")
    (output_dir / "manifest.json").write_text(json.dumps(manifest(output_dir), indent=2))
    print(json.dumps({"output_dir": str(output_dir), "files": [str(json_path), str(md_path)]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
