# Qwen MPS Seed 42/43 Summary

Generated: `2026-06-03T09:39:46+0700`

## W5 Cross-Seed Means

| defense | mean W4 | mean W5 | mean ratio | W5 per seed |
|---|---:|---:|---:|---|
| B1_no_defense | 9.38% | 8.12% | 0.861x | [9.55, 6.7] |
| B2_temperature_0.5 | 12.95% | 10.27% | 0.793x | [11.34, 9.2] |
| B3_top_p_0.7 | 13.17% | 9.51% | 0.721x | [10.18, 8.84] |
| B5_content_filter | 11.38% | 6.70% | 0.586x | [7.68, 5.71] |
| LEAKCERT | 9.16% | 7.00% | 0.764x | [8.12, 5.89] |

## Per-Seed Notes
- seed42: B7 21.88%, W3 {'B1_no_defense': 20.0, 'B5_content_filter': 15.0, 'LEAKCERT': 10.0}, root `_run_results/local_mps_qwen_positive_expanded_20260603_070216`
- seed43: B7 12.5%, W3 {'B1_no_defense': 15.0, 'B5_content_filter': 12.5, 'LEAKCERT': 10.0}, root `_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323`
