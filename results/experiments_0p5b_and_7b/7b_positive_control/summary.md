# 7B positive control: exposure AUC and SPRT TPR/FPR

## Exposure (reference-ratio LLR)

Target: the over-memorised 7B checkpoint (1 epoch on 700 documents). Reference: the base Qwen2.5-Coder-7B model. Members seed 42, non-members seed 999.

| Group | n | mean LLR | median LLR |
|---|---:|---:|---:|
| member | 1132 | 96.58 | 21.53 |
| non-member | 1132 | 85.96 | 18.92 |

**AUC = 0.5686** (95% bootstrap CI over canaries [0.5452, 0.5919]), mean gap = 10.62 nats.

**Verdict:** AUC=0.569 <= 0.6: exposure does not separate members from non-members even on the over-memorized checkpoint.

| Canary type | AUC | mean gap (nats) |
|---|---:|---:|
| T1_literal | 0.566 | 2.03 |
| T2_paraphrase | 0.787 | 8.21 |
| T3_semantic | 0.700 | 32.29 |
| T4_vulnerability | 0.504 | -0.05 |

## Completion-based SPRT (members vs non-members)

| Defense | TPR % (95% CI) | FPR % (95% CI) | gap (pp) |
|---|---:|---:|---:|
| B1_no_defense | 100.0 (96.3-100.0, n=100) | 100.0 (96.3-100.0, n=100) | 0.0 |
| B5_content_filter | 84.0 (75.6-89.9, n=100) | 83.0 (74.5-89.1, n=100) | 1.0 |
| LEAKCERT | 82.0 (73.3-88.3, n=100) | 78.0 (68.9-85.0, n=100) | 4.0 |

A valid membership test needs TPR well above FPR. A gap near zero means the test responds to target-generated text, not membership.

## Caveats

- The 7B reference is the base 7B model, not a no-canary model trained on the same corpus.
- 7B was trained 1 epoch on 700 docs (`cc_sub700`), a scaled demonstration.
- The SPRT panel is 100 canaries (25 per type), so its intervals are wide.
