#!/usr/bin/env python3
"""Convert LCCT forbidden_questions.csv into labeled JSONL.

The official artifact lists 80 questions in four contiguous blocks of 20.
This script preserves the original text and adds category labels for audit.
It does not run the questions against a model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CATEGORIES = [
    "illegal_content",
    "hate_speech",
    "pornography",
    "harmful_content",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-jsonl", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    questions = [
        line.strip()
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    for idx, question in enumerate(questions):
        category_idx = min(idx // 20, len(CATEGORIES) - 1)
        rows.append(
            {
                "id": f"lcct_forbidden_{idx + 1:03d}",
                "category": CATEGORIES[category_idx],
                "question": question,
                "source": str(input_path),
                "notes": "Official public forbidden_questions.csv from Sensente/Security-Attacks-on-LCCTs.",
            }
        )
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    summary = {
        "input": str(input_path),
        "output_jsonl": str(output_path),
        "n_questions": len(rows),
        "category_counts": {
            category: sum(1 for row in rows if row["category"] == category)
            for category in CATEGORIES
        },
        "paper_grade_for_jailbreak_questions": len(rows) == 80,
        "author_confirmed_dataset": True,
        "author_confirmed_order": "Illegal - Hate - Pornography - Harmful",
        "category_mapping": {
            "rows_001_020": "illegal_content",
            "rows_021_040": "hate_speech",
            "rows_041_060": "pornography",
            "rows_061_080": "harmful_content",
        },
        "judge_prompt_status": "use_cited_appendix_b_construction",
        "judge_prompt_source": "https://arxiv.org/pdf/2310.03693 Appendix B",
        "training_data_extraction_artifact_status": "not_released_due_privacy",
    }
    (output_path.parent / "forbidden_questions_metadata.json").write_text(
        json.dumps(summary, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
