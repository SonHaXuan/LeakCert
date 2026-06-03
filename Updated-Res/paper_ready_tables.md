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

## Safe Claim Wording

> In a local positive-control evaluation with Qwen2.5-Coder-0.5B, the learned-only LEAKCERT refusal variant reduced W5 paraphrase extraction relative to the B5 content-filter baseline across two seeds. A 1M-sample bootstrap comparison showed B5 exceeded the learned-only method by 2.95 to 3.21 percentage points, with confidence intervals excluding zero. A matched W3 diagnostic showed identical pass@1 for B1, B5, and LEAKCERT, suggesting that the observed utility weakness is checkpoint-driven rather than caused by the defense layer.

## Claims To Avoid Until Server Runs Finish

- Do not claim full W1/W4/W5 scale.
- Do not claim DP-SGD epsilon sweep results.
- Do not claim multi-model robustness.
- Do not claim non-vacuous certificate tightness.
- Do not claim paper-grade LCCT training-data extraction reproduction.
