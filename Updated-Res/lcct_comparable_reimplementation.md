# LCCT Comparable Reimplementation

## Why This Exists

The original LCCT training-data extraction benchmark depends on user-level artifacts
that the authors cannot release due privacy concerns. This repository therefore
implements a **comparable controlled benchmark**, not a paper-grade reproduction
of the original user-level extraction artifact.

## What Is Implemented

- `scripts/prepare_lcct_comparable_benchmark.py`
  - creates synthetic GitHub-profile/code-completion extraction prompts
  - stores controlled ground truth in JSONL
  - supports full-size comparable generation with `--target-prompts 4832`
  - marks every row as `synthetic_no_real_user_pii`

- `scripts/score_lcct_comparable.py`
  - scores completions against the benchmark
  - supports exact secret/email matching
  - supports fuzzy location matching by exact location, city subset, or component subset
  - reports overall and per-category hit rates

## Local Commands

```bash
OUT=_run_results/lcct_comparable_fullsize_$(date +%Y%m%d_%H%M%S)
.venv/bin/python scripts/prepare_lcct_comparable_benchmark.py \
  --output-dir "$OUT/benchmark" \
  --target-prompts 4832 \
  --seed 20260603

.venv/bin/python scripts/score_lcct_comparable.py \
  --benchmark "$OUT/benchmark/lcct_comparable_benchmark.jsonl" \
  --output-dir "$OUT/scorer_smoke" \
  --make-mock-completions
```

## Current Full-Size Smoke

The current full-size local smoke generated `4,832` prompts and verified the
scorer with deterministic mock completions. The benchmark JSONL itself is not
stored in this public result package because the synthetic strings intentionally
look like credentials and may trigger secret-scanning systems. Regenerate it
locally from the script when needed.

## Safe Claim Wording

> Since the original LCCT user-level extraction artifacts are unavailable for
> privacy reasons, we evaluate a controlled LCCT-style benchmark with synthetic
> ground truth. We report this as a comparable reimplementation, not a direct
> reproduction of the original LCCT training-data extraction artifact.
