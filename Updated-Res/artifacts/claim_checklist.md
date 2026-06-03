# Claim Checklist

- generated: `2026-06-01T16:58:43+0700`

| Claim | Status | Evidence | Note |
| --- | --- | --- | --- |
| Small-scale positive-control W4/W5 leakage reduction | `ready` | `_run_results/repeated_w4_w5_mps_20260530_132515/repeated_w4_w5_summary.json` | Strongest current empirical signal; can be claimed as bounded/small-scale. |
| W3 multilingual utility on HumanEvalPack | `ready_with_caveat` | `_run_results/w3_humanevalpack_multilingual_optimized_20260531/w3/w3_utility.json` | Valid run over 984 tasks, but absolute pass@1 is low. |
| Forbidden-questions jailbreak dataset availability | `ready_author_confirmed` | `_run_results/lcct_forbidden_questions_20260601_1328/data/forbidden_questions_metadata.json` | Authors confirmed the public CSV is the exact 80-question set and category order is Illegal-Hate-Pornography-Harmful. |
| Forbidden-questions safe harness | `ready_no_generation` | `_run_results/forbidden_questions_harness_20260601_1328/forbidden_questions_harness.json` | Prepared without generating harmful answers. |
| Forbidden-questions OpenRouter judge reimplementation | `ready_author_confirmed_reimplementation` | `_run_results/forbidden_questions_openrouter_judge_20260601_0650/full/summary.json` | Judge construction is author-confirmed as Appendix B of arXiv:2310.03693; exact model/version remains a reimplementation. |
| HCR public supplementary leakage smoke | `supplementary_only` | `_run_results/hcr_w2_supplement_20260531_2346/w2/w2_lcct_results.json` | Only 3 public examples; not a replacement for LCCT leakage full. |
| Certificate non-vacuous bound | `diagnostic_repair_plan_ready` | `_run_results/certificate_repair_plan_20260601_1650/certificate_repair_plan.md` | Current bound is vacuous; repair requires separating prior entropy from incremental leakage and using lower-KL DP/regularized checkpoints. |
| LCCT training-data extraction comparable reimplementation | `planned_due_artifact_unavailable` | `_run_results/lcct_comparable_reimplementation_20260601_1650/lcct_comparable_reimplementation_plan.md` | Authors declined release of user-level artifacts/extracted results due privacy; use controlled ground-truth comparable benchmark and disclose limitation. |
| DP sweep full | `blocked_missing_inputs` | `_run_results/submission_real_inputs_20260531_2312/real_input_validation.json` | Needs real corpus and per-epsilon DP checkpoints. |
| Multi-model full | `blocked_missing_inputs` | `_run_results/submission_real_inputs_20260531_2312/real_input_validation.json` | Needs real second-model ID/checkpoint and full corpus. |

## Decision

The current package is usable for a carefully scoped small-scale/submission-draft story, but full LCCT leakage must be framed as a comparable reimplementation because user-level artifacts are unavailable; DP sweep, multi-model full, and non-vacuous certificate claims still need stronger evidence.
