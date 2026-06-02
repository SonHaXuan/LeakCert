#!/usr/bin/env python3
"""Generate a claim-readiness checklist for SP writing."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path


CLAIMS = [
    {
        "claim": "Small-scale positive-control W4/W5 leakage reduction",
        "status": "ready",
        "evidence": "_run_results/repeated_w4_w5_mps_20260530_132515/repeated_w4_w5_summary.json",
        "note": "Strongest current empirical signal; can be claimed as bounded/small-scale.",
    },
    {
        "claim": "W3 multilingual utility on HumanEvalPack",
        "status": "ready_with_caveat",
        "evidence": "_run_results/w3_humanevalpack_multilingual_optimized_20260531/w3/w3_utility.json",
        "note": "Valid run over 984 tasks, but absolute pass@1 is low.",
    },
    {
        "claim": "Forbidden-questions jailbreak dataset availability",
        "status": "ready_author_confirmed",
        "evidence": "_run_results/lcct_forbidden_questions_20260601_1328/data/forbidden_questions_metadata.json",
        "note": "Authors confirmed the public CSV is the exact 80-question set and category order is Illegal-Hate-Pornography-Harmful.",
    },
    {
        "claim": "Forbidden-questions safe harness",
        "status": "ready_no_generation",
        "evidence": "_run_results/forbidden_questions_harness_20260601_1328/forbidden_questions_harness.json",
        "note": "Prepared without generating harmful answers.",
    },
    {
        "claim": "Forbidden-questions OpenRouter judge reimplementation",
        "status": "ready_author_confirmed_reimplementation",
        "evidence": "_run_results/forbidden_questions_openrouter_judge_20260601_0650/full/summary.json",
        "note": "Judge construction is author-confirmed as Appendix B of arXiv:2310.03693; exact model/version remains a reimplementation.",
    },
    {
        "claim": "HCR public supplementary leakage smoke",
        "status": "supplementary_only",
        "evidence": "_run_results/hcr_w2_supplement_20260531_2346/w2/w2_lcct_results.json",
        "note": "Only 3 public examples; not a replacement for LCCT leakage full.",
    },
    {
        "claim": "Certificate non-vacuous bound",
        "status": "diagnostic_repair_plan_ready",
        "evidence": "_run_results/certificate_repair_plan_20260601_1650/certificate_repair_plan.md",
        "note": "Current bound is vacuous; repair requires separating prior entropy from incremental leakage and using lower-KL DP/regularized checkpoints.",
    },
    {
        "claim": "LCCT training-data extraction comparable reimplementation",
        "status": "planned_due_artifact_unavailable",
        "evidence": "_run_results/lcct_comparable_reimplementation_20260601_1650/lcct_comparable_reimplementation_plan.md",
        "note": "Authors declined release of user-level artifacts/extracted results due privacy; use controlled ground-truth comparable benchmark and disclose limitation.",
    },
    {
        "claim": "DP sweep full",
        "status": "blocked_missing_inputs",
        "evidence": "_run_results/sp2027_real_inputs_20260531_2312/real_input_validation.json",
        "note": "Needs real corpus and per-epsilon DP checkpoints.",
    },
    {
        "claim": "Multi-model full",
        "status": "blocked_missing_inputs",
        "evidence": "_run_results/sp2027_real_inputs_20260531_2312/real_input_validation.json",
        "note": "Needs real second-model ID/checkpoint and full corpus.",
    },
]


def exists(path: str) -> bool:
    return Path(path).exists()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for claim in CLAIMS:
        row = dict(claim)
        row["evidence_exists"] = exists(row["evidence"])
        rows.append(row)

    report = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
        },
        "claims": rows,
        "summary": {
            "ready": sum(1 for row in rows if row["status"].startswith("ready")),
            "supplementary": sum(1 for row in rows if row["status"] == "supplementary_only"),
            "blocked": sum(1 for row in rows if row["status"].startswith("blocked")),
            "not_ready": sum(1 for row in rows if row["status"] == "not_ready"),
        },
    }
    (output_dir / "sp_claim_checklist.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# SP Claim Checklist",
        "",
        f"- generated: `{report['metadata']['timestamp']}`",
        "",
        "| Claim | Status | Evidence | Note |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = f"`{row['evidence']}`" if row["evidence_exists"] else f"`{row['evidence']}` (missing)"
        lines.append(f"| {row['claim']} | `{row['status']}` | {evidence} | {row['note']} |")
    lines.extend([
        "",
        "## Decision",
        "",
        "The current package is usable for a carefully scoped small-scale/submission-draft story, "
        "but full LCCT leakage must be framed as a comparable reimplementation because user-level artifacts are unavailable; DP sweep, multi-model full, and non-vacuous certificate claims still need stronger evidence.",
    ])
    (output_dir / "sp_claim_checklist.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output_dir": str(output_dir), "claims": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
