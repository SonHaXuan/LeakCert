# Repetition sweep, combined (R = 1, 4, 16, 64, 128, 256)

## Exposure AUC, members vs non-members (95% canary bootstrap CI)

| R | same-template, no-canary ref | same-template, base ref | template-disjoint, no-canary ref | template-disjoint, base ref |
|---|---|---|---|---|
| 256 | 0.823 [0.806, 0.841] | 0.824 [0.807, 0.841] | 0.996 [0.995, 0.997] | 0.985 [0.981, 0.989] |

## SPRT detection rate %, [exact 95% CI]: members / same-template non-members / template-disjoint non-members

### B1_no_defense

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 256 | 99.5 [97, 100] | 99.5 [97, 100] | 100.0 [98, 100] |

### B5_content_filter

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 256 | 82.0 [76, 87] | 82.5 [77, 87] | 94.0 [90, 97] |

### LEAKCERT

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 256 | 82.0 [76, 87] | 81.5 [75, 87] | 90.0 [85, 94] |

## Extraction by repeat count

Verbatim rate (%) of the SPRT run on members, B1 (no defense), overall and T4; and the undefended W4/W5 extraction on part C of the nested defense evaluation.

| R | SPRT verbatim, B1 overall | SPRT verbatim, B1 T4 | nested W4 B1 % | nested W5 B1 % | nested W4 T1 B1 % |
|---|---|---|---|---|---|
| 256 | 16.5 | 64.0 | 3.69 | 1.15 | 0.18 |

## Nested defense evaluation (part C only; B5 minus learned-only, canary-level bootstrap)

| R | frozen t | W5 B1 % | W5 B5 % | W5 learned-only % | W5 diff pp [95% CI] | W5 P(B5>ours) |
|---|---|---|---|---|---|---|
| 256 | 0.99 | 1.15 | 1.11 | 1.11 | 0.000 [0.000, 0.000] | 0.000 |
