# Entropy-Cap Audit

Invariant: every mutual-information, certificate, or DP-bound quantity must satisfy `value <= H(K)`.

Raw historical values are preserved as diagnostics. Reviewer-facing values should use the capped columns.

## File Summary

| source | H(K) | H source | checked | raw violations | capped values | pass |
|---|---:|---|---:|---:|---:|---|
| `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table1_certificate.json` | 5.971 | `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table4_prior.json` | 21 | 20 | 20 | False |
| `_run_results/certificate_refresh_20260531_2349/certificate/table1_certificate.json` | 5.971 | `_run_results/certificate_refresh_20260531_2349/certificate/table4_prior.json` | 12 | 12 | 12 | False |
| `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table1_certificate.json` | 5.971 | `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 15 | 0 | 0 | True |
| `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table1_certificate.json` | 5.971 | `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 12 | 0 | 0 | True |
| `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table3_tightness.json` | 5.971 | `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table4_prior.json` | 12 | 11 | 11 | False |
| `_run_results/certificate_refresh_20260531_2349/certificate/table3_tightness.json` | 5.971 | `_run_results/certificate_refresh_20260531_2349/certificate/table4_prior.json` | 8 | 8 | 8 | False |
| `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table3_tightness.json` | 5.971 | `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 10 | 5 | 5 | False |
| `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table3_tightness.json` | 5.971 | `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 8 | 4 | 4 | False |
| `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table4_prior.json` | 5.971 | `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table4_prior.json` | 2 | 2 | 2 | False |
| `_run_results/certificate_refresh_20260531_2349/certificate/table4_prior.json` | 5.971 | `_run_results/certificate_refresh_20260531_2349/certificate/table4_prior.json` | 2 | 2 | 2 | False |
| `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 5.971 | `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 2 | 2 | 2 | False |
| `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 5.971 | `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 2 | 2 | 2 | False |
| `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table8_dp_comparison.json` | 5.971 | `_run_results/certificate_cpu_bounded_20260531_0344/certificate/table4_prior.json` | 10 | 10 | 10 | False |
| `_run_results/certificate_refresh_20260531_2349/certificate/table8_dp_comparison.json` | 5.971 | `_run_results/certificate_refresh_20260531_2349/certificate/table4_prior.json` | 10 | 10 | 10 | False |
| `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table8_dp_comparison.json` | 5.971 | `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 10 | 10 | 10 | False |
| `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table8_dp_comparison.json` | 5.971 | `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 10 | 10 | 10 | False |
| `_run_results/safe_real_suite_positive_control_20260528_120114/table1_certificate_sweep.json` | 5.971 | `_run_results/safe_real_suite_positive_control_20260528_120114/certificate/table4_prior.json` | 5 | 0 | 0 | True |
| `_run_results/safe_real_suite_positive_control_20260528_204722/table1_certificate_sweep.json` | missing | `missing` | 0 | 0 | 0 | None |
| `_run_results/safe_real_suite_positive_control_20260528_212720/table1_certificate_sweep.json` | missing | `missing` | 0 | 0 | 0 | None |
| `_run_results/safe_real_suite_positive_control_stable_20260528_190051/table1_certificate_sweep.json` | missing | `missing` | 0 | 0 | 0 | None |
| `_run_results/safe_real_suite_positive_control_stable_20260528_220342/table1_certificate_sweep.json` | missing | `missing` | 0 | 0 | 0 | None |
| `_run_results/safe_real_suite_tiny_20260527_232346/table1_certificate_sweep.json` | missing | `missing` | 0 | 0 | 0 | None |
| `_run_results/safe_real_suite_tiny_20260528_085312/table1_certificate_sweep.json` | 5.971 | `_run_results/safe_real_suite_tiny_20260528_085312/certificate/table4_prior.json` | 4 | 0 | 0 | True |

## Reviewer-Facing Interpretation

The audit found `108` raw values above the entropy ceiling. These rows must not be used as certificate-tightness claims without the capped columns.

Recommended paper action:

- Report `raw_*` only as diagnostic/unbounded composition quantities.
- Use `*_capped` for MI/certificate claims.
- Do not compute tightness ratios against uncapped MINE.
- Include `entropy_cap_pass` in table-generation CI.
