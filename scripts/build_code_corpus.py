#!/usr/bin/env python3
"""Build a fine-tuning code corpus from a HuggingFace dataset.

Writes a JSONL file with one ``{"text": ...}`` record per document, which is the
format expected by ``CorpusInjector`` and ``CanaryFineTuner`` (see
``leakcert/canary/injector.py`` and ``leakcert/model/fine_tuner.py``).

This is the W1 base corpus *before* canary injection. The paper spec is a
~12B-token GitHub corpus; that full size is rarely practical, so the size is
controlled with ``--max-rows`` / ``--max-tokens`` and defaults to a large but
tractable subset. Streaming is used so the whole dataset never lands on disk.

Examples
--------
# Default: Python from codeparrot/github-code-clean, ~2M docs
python scripts/build_code_corpus.py --output data/code_corpus.jsonl --max-rows 2000000

# Multi-language slice with an approximate token budget
python scripts/build_code_corpus.py \
    --dataset codeparrot/github-code-clean \
    --languages Python JavaScript Go \
    --max-tokens 2_000_000_000 \
    --output data/code_corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger("build_code_corpus")

# Candidate fields that hold the source text, in priority order. Different code
# datasets name this differently (github-code -> "code", the-stack -> "content").
_TEXT_FIELDS = ("code", "content", "text", "func_code_string", "whole_func_string")

# Rough chars-per-token estimate for the token-budget heuristic (code ~ 3.5).
_CHARS_PER_TOKEN = 3.5


def _pick_text_field(record: dict, override: str | None) -> str | None:
    if override:
        return override if override in record else None
    for field in _TEXT_FIELDS:
        if field in record and isinstance(record[field], str):
            return field
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dataset",
        default="codeparrot/codeparrot-clean",
        help="HuggingFace dataset id (default: %(default)s). "
        "Must be parquet-native; modern datasets>=3 cannot run "
        "script-based loaders like codeparrot/github-code-clean.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Dataset config/subset name, if the dataset requires one",
    )
    parser.add_argument("--split", default="train")
    parser.add_argument(
        "--text-field",
        default=None,
        help="Force which field holds the code text (auto-detected otherwise)",
    )
    parser.add_argument(
        "--language-field",
        default="language",
        help="Record field used by --languages filtering (default: %(default)s)",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        help="Keep only these languages (matched against --language-field)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=2_000_000,
        help="Stop after writing this many documents (default: %(default)s)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Approx token budget (chars/%.1f); stops when reached" % _CHARS_PER_TOKEN,
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=64,
        help="Skip documents shorter than this (default: %(default)s)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=100_000,
        help="Skip documents longer than this (default: %(default)s)",
    )
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="Load the full split into memory instead of streaming",
    )
    parser.add_argument(
        "--token", default=None, help="HuggingFace token (else uses env/login)"
    )
    parser.add_argument("--log-every", type=int, default=50_000)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        raise SystemExit("The 'datasets' package is required: pip install datasets")

    languages = {lang.lower() for lang in args.languages} if args.languages else None

    logger.info(
        "Loading %s (config=%s, split=%s, streaming=%s)",
        args.dataset,
        args.config,
        args.split,
        not args.no_streaming,
    )
    dataset = load_dataset(
        args.dataset,
        args.config,
        split=args.split,
        streaming=not args.no_streaming,
        token=args.token,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    approx_tokens = 0
    skipped = 0
    text_field: str | None = None

    with output.open("w", encoding="utf-8") as fout:
        for record in dataset:
            if text_field is None:
                text_field = _pick_text_field(record, args.text_field)
                if text_field is None:
                    raise SystemExit(
                        f"Could not find a text field in record keys {list(record)}; "
                        f"pass --text-field explicitly."
                    )
                logger.info("Using text field: %s", text_field)

            if languages is not None:
                lang = str(record.get(args.language_field, "")).lower()
                if lang not in languages:
                    skipped += 1
                    continue

            text = record.get(text_field) or ""
            if not isinstance(text, str):
                skipped += 1
                continue
            n_chars = len(text)
            if n_chars < args.min_chars or n_chars > args.max_chars:
                skipped += 1
                continue

            fout.write(json.dumps({"text": text}) + "\n")
            written += 1
            approx_tokens += int(n_chars / _CHARS_PER_TOKEN)

            if written % args.log_every == 0:
                logger.info(
                    "written=%d approx_tokens=%d skipped=%d",
                    written,
                    approx_tokens,
                    skipped,
                )

            if args.max_rows and written >= args.max_rows:
                logger.info("Reached --max-rows=%d", args.max_rows)
                break
            if args.max_tokens and approx_tokens >= args.max_tokens:
                logger.info("Reached --max-tokens=%d", args.max_tokens)
                break

    summary = {
        "dataset": args.dataset,
        "config": args.config,
        "split": args.split,
        "text_field": text_field,
        "languages": sorted(languages) if languages else None,
        "documents_written": written,
        "approx_tokens": approx_tokens,
        "documents_skipped": skipped,
        "output": str(output),
    }
    (output.with_suffix(".manifest.json")).write_text(json.dumps(summary, indent=2))
    logger.info("Done. %s", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
