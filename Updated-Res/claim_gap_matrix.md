# Claim Gap Matrix

| Evaluation item | Current status | Current evidence | Submission risk |
|---|---|---|---|
| W1 canary fine-tune | Partial | Positive-control Qwen runs, small panels | Full paper scope needs larger corpus, larger canary set, more panels, more models |
| W2 LCCT forbidden questions | Ready as reimplementation | Authors confirmed exact 80-question CSV and category order | Judge is reimplemented, not exact private framework |
| W2 LCCT training-data extraction | Comparable only | Public user-level artifacts unavailable | Must disclose limitation; cannot claim paper-grade reproduction |
| W3 utility | Diagnostic complete | B1/B5/LEAKCERT all 10.98% on W3-164 | Absolute utility too low for strong headline |
| W4 extraction | Good small-scale evidence | Seeded Qwen positive-control results | Not full 7,900-prompt scale |
| W5 paraphrase | Strongest evidence | Learned-only t=0.95 beats B5 across two seeds with bootstrap | Still small/medium scale |
| B2/B3 sweeps | Partial | Local sweeps exist for temperature/top-p | Not full table/scale |
| B4 rate limit | Smoke/partial | Local smoke exists | Needs full budget framing |
| B5 content filter | Covered | Used as main baseline | Learned-only result should compare directly against it |
| B6 DP-SGD | Not full | DP smoke only | Needs real DP checkpoints for eps={1,2,4,8,16} |
| B7/B8 adaptive attacks | Partial | B7/Carlini-style smoke and W5 paraphrase evidence | Needs full attack table at target budget |
| Certificate non-vacuous | Not ready | Current certificate diagnostic/vacuous | Needs repair before headline |
| Multi-model full | Not ready | No second full checkpoint | Needs server/GPU or equivalent |
