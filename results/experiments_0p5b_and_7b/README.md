# Experiment results: repetition sweep (0.5B) and 7B positive control

Measured results only (tables as Markdown, raw outputs as JSON). No source code is included in this folder.

## Contents

| Folder | What it contains |
|---|---|
| `7b_positive_control/` | Exposure AUC and completion-based SPRT (TPR on members, FPR on non-members) for the over-memorised 7B checkpoint, with a per-type breakdown and a 400-canary SPRT panel |
| `repsweep_0p5b/` | Qwen2.5-Coder-0.5B trained with 1,000 canaries repeated R = 1, 4, 16, 64, 128 times: exposure AUC and SPRT by R, a template-disjoint non-member panel, and a nested tune-freeze-evaluate defense evaluation |

## Files

- `7b_positive_control/summary.md`, `by_type.md`, `sprt_n400.md` and the JSON files next to them.
- `repsweep_0p5b/exposure_and_sprt.md`: exposure AUC (matched no-canary and base references), per-type AUC, SPRT TPR/FPR, verbatim extraction.
- `repsweep_0p5b/template_disjoint.md`: the same measurements against non-members built from held-out templates.
- `repsweep_0p5b/defense_nested.md`: B1 / B5 / learned-only extraction on a held-out part of the canary panel, with canary-level bootstrap intervals (runs r16, r64, r128).
- `repsweep_0p5b/combined_summary.md`: one table set with 95% intervals for every R.
- `repsweep_0p5b/raw/<run>/`: raw summary JSON per run (`c1` = same-template non-members, `c1_td` = template-disjoint non-members, `lrt_run/lrt/table11_lrt*.json` = SPRT, `defense_nested/nested_summary.json` = nested defense).

## Setup in one paragraph

Exposure is a reference-ratio log-likelihood ratio of a canary under the target model versus a reference model; AUC compares members (canary seed 42) with non-members (seed 999). The SPRT is the completion-based A-greedy-LRT; its TPR is measured on members and its FPR on non-members. For the 0.5B sweep the training corpus is 50K clean documents plus 1,000 canaries repeated R times (1 epoch), and a no-canary model trained on the same corpus is the matched reference. The 7B checkpoint was trained for 1 epoch on 700 documents and uses the base 7B model as reference.

## Main numbers

| Measurement | Result |
|---|---|
| 7B exposure AUC (members vs non-members) | 0.569, 95% CI [0.545, 0.592] |
| 7B SPRT, 400 canaries (B1 / B5 / LeakCert), TPR vs FPR % | 100.0 vs 100.0 / 84.75 vs 83.0 / 82.25 vs 82.25 |
| 0.5B exposure AUC, R = 1 / 4 / 16 / 64 / 128 | 0.492 / 0.502 / 0.552 / 0.788 / 0.813 |
| 0.5B SPRT B1, TPR vs FPR % at R = 1 / 128 | 100.0 vs 99.0 / 99.5 vs 97.0 |
| Exposure AUC against template-disjoint non-members, R = 1 to 128 | 0.956 to 0.997 |
| Nested defense, W5 extraction on held-out part (B1 / B5 / learned-only) at R=16, 64, 128 | 0.47 / 0.46 / 0.42, 0.79 / 0.79 / 0.78, 0.95 / 0.95 / 0.95 (%) |

## Limits

One training run per R (intervals are within-run only), one non-member seed, 100 to 400 canaries per SPRT panel, and 164 HumanEval problems for the utility side of the defense evaluation. The 7B reference is the base model, not a no-canary model trained on the same corpus.
