#!/usr/bin/env python3
"""Convert the public HCR examples into W2-compatible supplementary JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_secret_regex(path: Path) -> dict[str, dict[str, str]]:
    rows = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[row["secret_id"]] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hcr-dir", required=True)
    parser.add_argument("--output-jsonl", required=True)
    args = parser.parse_args()

    hcr_dir = Path(args.hcr_dir)
    output_jsonl = Path(args.output_jsonl)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    regex_by_secret = load_secret_regex(hcr_dir / "secret_re_list.csv")
    examples = []
    with (hcr_dir / "phase3_file_list.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        for row in csv.DictReader(handle):
            test_dir = hcr_dir / "test_folder_example" / f"test_{row['id']}"
            source_path = test_dir / row["file_name"]
            if not source_path.exists():
                continue
            secret_meta = regex_by_secret[row["secret_type"]]
            prompt = source_path.read_text(encoding="utf-8")
            examples.append(
                {
                    "id": f"hcr_{row['id']}",
                    "prompt": prompt,
                    "expected_regex": secret_meta["RE"],
                    "metadata": {
                        "category": row["secret_type"],
                        "source": "HCR public test_folder_example",
                        "source_file": str(source_path),
                        "provider": secret_meta.get("Provider", ""),
                        "domain": secret_meta.get("Domain", ""),
                        "paper_grade": False,
                        "notes": "Supplementary public HCR example; not a replacement for full LCCT.",
                    },
                }
            )

    with output_jsonl.open("w", encoding="utf-8") as handle:
        for item in examples:
            handle.write(json.dumps(item) + "\n")
    metadata = {
        "n_examples": len(examples),
        "source": str(hcr_dir),
        "output_jsonl": str(output_jsonl),
        "paper_grade": False,
        "citation_note": "HCR public artifact contains only three demo examples; use as supplementary smoke only.",
    }
    (output_jsonl.parent / "hcr_w2_supplement_metadata.json").write_text(
        json.dumps(metadata, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
