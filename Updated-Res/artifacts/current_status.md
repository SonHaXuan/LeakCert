# Current Project Status

- generated: `2026-06-03T20:19:16+0700`
- hostname: `local-mac`

## Completed Since Last Update

- LCCT forbidden questions cloned and labeled: 80 queries, 4 categories x 20; authors confirmed exact dataset and category order.
- HCR supplementary W2-style smoke completed: 3 public examples, 0/3 extraction for all defenses.
- W3 fallback run completed and is available as a replicate/check run.
- OpenRouter judge reimplementation completed for 80 forbidden questions; judge construction now matches author-confirmed Appendix B source.
- Certificate refresh completed: still vacuous; diagnostic only.
- LCCT user-level leakage artifact will not be released by authors due privacy; move to comparable reimplementation with explicit limitation.
- Local MPS Qwen positive-control expanded run completed: Phase A/B smoke plus W5 paraphrase table are available.

## Claim Readiness

- strong_small_scale_leakage: `True`
- w3_utility_multilingual: `True`
- w3_utility_multilingual_replicate: `True`
- forbidden_questions_available: `True`
- forbidden_questions_author_confirmed: `True`
- forbidden_questions_judge_reimplementation: `True`
- hcr_supplement_available: `True`
- lcct_leakage_full_available: `False`
- lcct_leakage_artifact_unreleased_due_privacy: `True`
- dp_sweep_full_available: `False`
- multi_model_full_available: `False`
- certificate_non_vacuous: `False`
- local_mps_qwen_positive_control_available: `True`

## Key Paths

- w3_multilingual: `_run_results/w3_humanevalpack_multilingual_optimized_20260531/w3/w3_utility.json`
- w3_multilingual_fallback: `_run_results/w3_humanevalpack_multilingual_after_mps_free_20260531/w3/w3_utility.json`
- w5_b2_b3: `_run_results/w5_b2_b3_after_mps_free_20260531/w5/table6_paraphrase_robustness.json`
- w4_w5_replicate: `_run_results/repeated_w4_w5_mps_20260530_132515/repeated_w4_w5_summary.json`
- hcr_supplement: `_run_results/hcr_w2_supplement_20260531_2346/w2/w2_lcct_results.json`
- hcr_metadata: `_run_results/hcr_w2_supplement_20260531_2346/w2/w2_metadata.json`
- certificate_refresh: `_run_results/certificate_refresh_20260531_2349/certificate/table1_certificate.json`
- forbidden_questions: `_run_results/lcct_forbidden_questions_20260601_1328/data/forbidden_questions_metadata.json`
- forbidden_questions_openrouter_judge: `_run_results/forbidden_questions_openrouter_judge_20260601_0650/full/summary.json`
- real_input_validation: `_run_results/submission_real_inputs_20260531_2312/real_input_validation.json`
- local_mps_qwen_phase_a: `_run_results/local_mps_qwen_positive_expanded_20260603_070216/phase_a/phase_a_smoke_summary.json`
- local_mps_qwen_phase_b: `_run_results/local_mps_qwen_positive_expanded_20260603_070216/phase_b/b2_b3_sweep_summary.json`
- local_mps_qwen_w5: `_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/table6_paraphrase_robustness.json`
