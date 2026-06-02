#!/usr/bin/env python3
"""Write a compact status report for the current SP evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths = {
        "w3_multilingual": Path("_run_results/w3_humanevalpack_multilingual_optimized_20260531/w3/w3_utility.json"),
        "w3_multilingual_fallback": Path("_run_results/w3_humanevalpack_multilingual_after_mps_free_20260531/w3/w3_utility.json"),
        "w5_b2_b3": Path("_run_results/w5_b2_b3_after_mps_free_20260531/w5/table6_paraphrase_robustness.json"),
        "w4_w5_replicate": Path("_run_results/repeated_w4_w5_mps_20260530_132515/repeated_w4_w5_summary.json"),
        "hcr_supplement": Path("_run_results/hcr_w2_supplement_20260531_2346/w2/w2_lcct_results.json"),
        "hcr_metadata": Path("_run_results/hcr_w2_supplement_20260531_2346/w2/w2_metadata.json"),
        "certificate_refresh": Path("_run_results/certificate_refresh_20260531_2349/certificate/table1_certificate.json"),
        "forbidden_questions": Path("_run_results/lcct_forbidden_questions_20260601_1328/data/forbidden_questions_metadata.json"),
        "forbidden_questions_openrouter_judge": Path("_run_results/forbidden_questions_openrouter_judge_20260601_0650/full/summary.json"),
        "real_input_validation": Path("_run_results/sp2027_real_inputs_20260531_2312/real_input_validation.json"),
    }
    data = {name: load(path) for name, path in paths.items()}
    report = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
        },
        "paths": {name: str(path) for name, path in paths.items()},
        "artifacts": data,
        "claim_readiness": {
            "strong_small_scale_leakage": True,
            "w3_utility_multilingual": data["w3_multilingual"] is not None,
            "w3_utility_multilingual_replicate": data["w3_multilingual_fallback"] is not None,
            "forbidden_questions_available": bool(
                data["forbidden_questions"]
                and data["forbidden_questions"].get("paper_grade_for_jailbreak_questions")
            ),
            "forbidden_questions_author_confirmed": bool(
                data["forbidden_questions"]
                and data["forbidden_questions"].get("author_confirmed_dataset")
            ),
            "forbidden_questions_judge_reimplementation": data["forbidden_questions_openrouter_judge"] is not None,
            "hcr_supplement_available": bool(data["hcr_supplement"]),
            "lcct_leakage_full_available": False,
            "lcct_leakage_artifact_unreleased_due_privacy": True,
            "dp_sweep_full_available": False,
            "multi_model_full_available": False,
            "certificate_non_vacuous": False,
        },
        "notes": [
            "HCR public examples are supplementary only and do not replace full LCCT leakage.",
            "Authors confirmed forbidden_questions.csv is the exact 80-question set and the order is Illegal-Hate-Pornography-Harmful.",
            "Authors confirmed the judge construction follows Appendix B of arXiv:2310.03693; exact API/model settings should still be disclosed as reimplementation.",
            "Authors declined release of LCCT user-level leakage artifacts due privacy; full reproduction is unavailable from public artifacts.",
            "Certificate refresh remains vacuous and should be treated as diagnostic, not a main claim.",
        ],
    }
    (out / "current_sp_status.json").write_text(json.dumps(report, indent=2))

    lines = [
        "# Current SP Status",
        "",
        f"- generated: `{report['metadata']['timestamp']}`",
        f"- hostname: `{report['metadata']['hostname']}`",
        "",
        "## Completed Since Last Update",
        "",
        "- LCCT forbidden questions cloned and labeled: 80 queries, 4 categories x 20; authors confirmed exact dataset and category order.",
        "- HCR supplementary W2-style smoke completed: 3 public examples, 0/3 extraction for all defenses.",
        "- W3 fallback run completed and is available as a replicate/check run.",
        "- OpenRouter judge reimplementation completed for 80 forbidden questions; judge construction now matches author-confirmed Appendix B source.",
        "- Certificate refresh completed: still vacuous; diagnostic only.",
        "- LCCT user-level leakage artifact will not be released by authors due privacy; move to comparable reimplementation with explicit limitation.",
        "",
        "## Claim Readiness",
        "",
    ]
    for key, value in report["claim_readiness"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Key Paths", ""])
    for key, path in report["paths"].items():
        lines.append(f"- {key}: `{path}`")
    (out / "current_sp_status.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output_dir": str(out), "status": str(out / "current_sp_status.md")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
