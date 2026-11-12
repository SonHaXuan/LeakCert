# Repetition sweep on Qwen2.5-Coder-0.5B: exposure and SPRT

Setup: 50K clean documents plus 1,000 canaries repeated R times, 1 epoch, R in {1, 4, 16, 64, 128, 256}, plus a matched `--no-canary` reference model. Members use seed 42, non-members use seed 999 (1,132 canaries each for the exposure AUC; 200 canaries for the SPRT panel). Decision thresholds used to read the AUC: >= 0.8 the exposure score separates members from non-members, <= 0.6 it does not.

Raw files: `raw/<run>/c1/c1_summary_{nocanary,base}.json` (exposure), `raw/<run>/lrt_run/lrt/table11_lrt{,_fpcontrol}.json` (SPRT on members and on non-members).

## Exposure (reference-ratio LLR), member vs non-member AUC

| R | AUC (matched no-canary ref) | AUC (base ref) | KS | mean LLR gap |
|---|---|---|---|---|
| 1 | 0.492 | 0.490 | 0.031 | 0.1 |
| 4 | 0.502 | 0.503 | 0.029 | 1.1 |
| 16 | 0.552 | 0.550 | 0.123 | 5.3 |
| 64 | 0.788 | 0.788 | 0.516 | 134.6 |
| 128 | 0.813 | 0.813 | 0.527 | 160.2 |
| 256 | 0.823 | 0.824 | 0.537 | 166.1 |

95% canary-bootstrap intervals are in `combined_summary.md` (R=128: 0.813 [0.794, 0.831]; R=256: 0.823 [0.806, 0.841]).

Per-type AUC (matched ref): T1 literal / T2 paraphrase / T3 semantic / T4 vulnerability

| R | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| 1 | 0.518 | 0.432 | 0.526 | 0.520 |
| 4 | 0.532 | 0.478 | 0.551 | 0.520 |
| 16 | 0.639 | 0.637 | 0.605 | 0.520 |
| 64 | 1.000 | 1.000 | 0.915 | 0.528 |
| 128 | 1.000 | 1.000 | 0.997 | 0.527 |
| 256 | 1.000 | 1.000 | 0.998 | 0.527 |

## SPRT detection: TPR on members / FPR on non-members (%)

| R | B1 no defense | B5 content filter | LeakCert |
|---|---|---|---|
| 1 | 100.0 / 99.0 | 96.0 / 97.5 | 95.0 / 96.5 |
| 4 | 99.5 / 100.0 | 91.0 / 89.5 | 86.5 / 88.0 |
| 16 | 100.0 / 100.0 | 86.0 / 85.5 | 81.0 / 82.5 |
| 64 | 99.5 / 100.0 | 84.0 / 83.5 | 86.0 / 83.5 |
| 128 | 99.5 / 97.0 | 83.0 / 83.0 | 80.5 / 81.5 |
| 256 | 99.5 / 99.5 | 82.0 / 82.5 | 82.0 / 81.5 |

## Verbatim extraction in the SPRT run on members (B1, %)

| R | overall | T1 | T4 |
|---|---|---|---|
| 1 | 0.0 | 0.0 | 0.0 |
| 4 | 1.0 | n/a | 4.0 |
| 16 | 14.5 | ~0 | 58.0 |
| 64 | 14.5 | ~0 | 58.0 |
| 128 | 18.0 | 0.0 | 72.0 |
| 256 | 16.5 | 2.0 | 64.0 |

## Reading

- Exposure becomes a membership signal only at high repetition. It is at chance for R=1 and R=4 (AUC about 0.50), weak at R=16 (0.55), 0.788 at R=64, 0.813 at R=128 and 0.823 at R=256. The R=128 interval [0.794, 0.831] contains 0.8, so R=128 sits at the threshold; the R=256 interval [0.806, 0.841] lies entirely above it.
- T1 and T2 reach AUC 1.0 by R=64 and T3 reaches 0.997 by R=128 (0.998 at R=256), while T4 (vulnerability idioms) stays at chance (0.52 to 0.53) for every R. The overall AUC is held below 1.0 by T4.
- The matched no-canary reference and the base reference give the same AUC (to three decimals up to R=64, to within 0.001 at R=128 and R=256), so the choice of reference does not explain the result.
- SPRT does not track membership at any R. The detection rate on non-members is within 3 points of the rate on members for every R and defense, including R=128 and R=256 where exposure separates the groups (B1 99.5 vs 97.0 and 99.5 vs 99.5).
- Verbatim extraction grows with R up to R=128 (18.0%) and is 16.5% at R=256, so it does not increase monotonically. It is driven by T4 vulnerability idioms (T4 reaches 72% at R=128 and 64% at R=256, while T1 literal secrets stay at 0% to 2%).

Limits: one training run per R, so intervals are within-run only; one non-member seed; 200 canaries per SPRT panel.
