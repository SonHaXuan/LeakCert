# Paper-Ready Result Tables

These are the numbers that are most defensible to reuse in the current draft. They are intentionally scoped as local positive-control evidence, not full-scale claims.

## Table A: W5 Paraphrase Leakage Reduction

| Method | Seed | W4 extraction | W5 extraction | Robustness ratio | Interpretation |
|---|---:|---:|---:|---:|---|
| B5 content filter | 42 | 12.50% | 7.68% | 0.614x | baseline regex/content filter |
| learned-only LEAKCERT t=0.95 | 42 | 7.59% | 4.73% | 0.624x | lower W5 extraction than B5 |
| B5 content filter | 43 | 10.27% | 5.71% | 0.556x | baseline regex/content filter |
| learned-only LEAKCERT t=0.95 | 43 | 4.91% | 2.50% | 0.509x | strongest replicated result |

## Table B: Bootstrap Evidence for W5 Improvement

| Comparison | B5 - method | 95% CI | P(B5 > method) |
|---|---:|---:|---:|
| seed43 B5 vs learned-only t=0.95 | 3.214 pp | [1.607, 4.911] | 0.99993 |
| seed42 B5 vs learned-only t=0.95 | 2.946 pp | [0.982, 4.911] | 0.99787 |

## Table C: W3 Utility Diagnostic

| Defense | pass@1 | Correct / problems | Refusal |
|---|---:|---:|---:|
| B1 no defense | 10.98% | 18 / 164 | 0.00% |
| B5 content filter | 10.98% | 18 / 164 | 0.00% |
| learned-only LEAKCERT t=0.95 | 10.98% | 18 / 164 | 0.61% |

## Table D: Entropy-Cap Audit for Certificate/MI Tables

| checked values | raw violations | capped values | reviewer-facing action |
|---:|---:|---:|---|
| 155 | 108 | 108 | use capped certificate/MI columns; raw values are diagnostics only |

## Table E: Informative-Budget Pilot

| KL source | any non-vacuous capped certificate | interpretation |
|---|---|---|
| certificate_refresh | False | high-leakage diagnostic; certificate saturates immediately |
| safe_positive | True | low/zero-KL diagnostic; verifies non-vacuous regime path |

## Table F: Mac Studio Stable W5 Replication Queue

| seed | B5 W4 | B5 W5 | learned-only W4 | learned-only W5 | status |
|---|---:|---:|---:|---:|---|
| 44 | 8.48 | 5.8 | 3.57 | 2.68 | complete |
| 45 | 11.16 | 6.61 | 5.8 | 2.77 | complete |
| 46 | 8.04 | 4.11 | 2.68 | 1.52 | complete |


## Safe Claim Wording

> In a local positive-control evaluation with Qwen2.5-Coder-0.5B, the learned-only LEAKCERT refusal variant reduced W5 paraphrase extraction relative to the B5 content-filter baseline across two seeds. A 1M-sample bootstrap comparison showed B5 exceeded the learned-only method by 2.95 to 3.21 percentage points, with confidence intervals excluding zero. A matched W3 diagnostic showed identical pass@1 for B1, B5, and LEAKCERT, suggesting that the observed utility weakness is checkpoint-driven rather than caused by the defense layer.

> Certificate and MI quantities are now treated with an explicit entropy ceiling. Historical raw certificate/MI values that exceed `H(K)` are retained only as diagnostics; reviewer-facing tables must report capped quantities and a pass/fail entropy audit.

## Claims To Avoid Until Server Runs Finish

- Do not claim full W1/W4/W5 scale.
- Do not claim DP-SGD epsilon sweep results.
- Do not claim multi-model robustness.
- Do not claim non-vacuous certificate tightness.
- Do not claim paper-grade LCCT training-data extraction reproduction.
