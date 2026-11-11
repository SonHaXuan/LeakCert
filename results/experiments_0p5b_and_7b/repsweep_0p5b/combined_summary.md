# Repetition sweep, combined (R = 1, 4, 16, 64, 128)

## Exposure AUC, members vs non-members (95% canary bootstrap CI)

| R | same-template, no-canary ref | same-template, base ref | template-disjoint, no-canary ref | template-disjoint, base ref |
|---|---|---|---|---|
| 1 | 0.492 [0.469, 0.516] | 0.490 [0.467, 0.515] | 0.956 [0.948, 0.964] | 0.876 [0.862, 0.890] |
| 4 | 0.502 [0.480, 0.526] | 0.503 [0.480, 0.526] | 0.960 [0.953, 0.967] | 0.919 [0.909, 0.930] |
| 16 | 0.552 [0.529, 0.575] | 0.550 [0.527, 0.574] | 0.965 [0.959, 0.972] | 0.940 [0.932, 0.949] |
| 64 | 0.788 [0.768, 0.807] | 0.788 [0.768, 0.808] | 0.997 [0.996, 0.998] | 0.986 [0.982, 0.989] |
| 128 | 0.813 [0.794, 0.831] | 0.813 [0.795, 0.831] | 0.997 [0.996, 0.998] | 0.982 [0.978, 0.986] |

## SPRT detection rate %, [exact 95% CI]: members / same-template non-members / template-disjoint non-members

### B1_no_defense

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 1 | 100.0 [98, 100] | 99.0 [96, 100] | 98.5 [96, 100] |
| 4 | 99.5 [97, 100] | 100.0 [98, 100] | 99.0 [96, 100] |
| 16 | 100.0 [98, 100] | 100.0 [98, 100] | 98.5 [96, 100] |
| 64 | 99.5 [97, 100] | 100.0 [98, 100] | 99.5 [97, 100] |
| 128 | 99.5 [97, 100] | 97.0 [94, 99] | 100.0 [98, 100] |

### B5_content_filter

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 1 | 96.0 [92, 98] | 97.5 [94, 99] | 98.0 [95, 99] |
| 4 | 91.0 [86, 95] | 89.5 [84, 93] | 96.5 [93, 99] |
| 16 | 86.0 [80, 90] | 85.5 [80, 90] | 95.5 [92, 98] |
| 64 | 84.0 [78, 89] | 83.5 [78, 88] | 93.5 [89, 96] |
| 128 | 83.0 [77, 88] | 83.0 [77, 88] | 90.5 [86, 94] |

### LEAKCERT

| R | members (TPR) | same-template (FPR) | template-disjoint (FPR) |
|---|---|---|---|
| 1 | 95.0 [91, 98] | 96.5 [93, 99] | 98.5 [96, 100] |
| 4 | 86.5 [81, 91] | 88.0 [83, 92] | 95.0 [91, 98] |
| 16 | 81.0 [75, 86] | 82.5 [77, 87] | 91.0 [86, 95] |
| 64 | 86.0 [80, 90] | 83.5 [78, 88] | 91.5 [87, 95] |
| 128 | 80.5 [74, 86] | 81.5 [75, 87] | 90.5 [86, 94] |

## Extraction by repeat count

Verbatim rate (%) of the SPRT run on members, B1 (no defense), overall and T4; and the undefended W4/W5 extraction on part C of the nested defense evaluation.

| R | SPRT verbatim, B1 overall | SPRT verbatim, B1 T4 | nested W4 B1 % | nested W5 B1 % | nested W4 T1 B1 % |
|---|---|---|---|---|---|
| 1 | 0.0 | 0.0 | n/a | n/a | n/a |
| 4 | 1.0 | 4.0 | n/a | n/a | n/a |
| 16 | 14.5 | 58.0 | 2.60 | 0.47 | 0.00 |
| 64 | 14.5 | 58.0 | 3.22 | 0.79 | 0.06 |
| 128 | 18.0 | 72.0 | 4.00 | 0.95 | 0.18 |

## Nested defense evaluation (part C only; B5 minus learned-only, canary-level bootstrap)

| R | frozen t | W5 B1 % | W5 B5 % | W5 learned-only % | W5 diff pp [95% CI] | W5 P(B5>ours) |
|---|---|---|---|---|---|---|
| 16 | 0.7 | 0.47 | 0.46 | 0.42 | 0.046 [0.011, 0.098] | 0.982 |
| 64 | 0.7 | 0.79 | 0.79 | 0.78 | 0.012 [0.000, 0.037] | 0.639 |
| 128 | 0.99 | 0.95 | 0.95 | 0.95 | 0.000 [0.000, 0.000] | 0.000 |
