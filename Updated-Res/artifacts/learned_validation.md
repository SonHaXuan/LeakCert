# Learned-Only t=0.95 Validation Summary

Generated: `2026-06-03T19:35:37+0700`

## Utility / Refusal

- W3-164 pass@1: `6.71%` (11/164)
- W3-164 refusal: `3.05%`

## W5 Extraction

| seed | W4 | W5 | ratio |
|---|---:|---:|---:|
| seed43 | 4.91% | 2.50% | 0.509x |
| seed42 | 7.59% | 4.73% | 0.624x |

## Bootstrap Evidence

# Bootstrap W5 Evidence

Generated: `2026-06-03T19:35:14+0700`
Workers: `24`, bootstrap samples per comparison: `1000000`

| comparison | baseline W5 | method W5 | baseline-method | 95% CI | P(baseline > method) |
|---|---:|---:|---:|---:|---:|
| seed43_B5_vs_LEAKCERT | 5.714% | 5.893% | -0.179 pp | [-2.143, 1.786] | 0.41045 |
| seed42_B5_vs_LEAKCERT | 7.679% | 8.125% | -0.446 pp | [-2.679, 1.786] | 0.33287 |
| seed43_B5_vs_calibrated_aggressive | 5.714% | 2.321% | 3.393 pp | [1.786, 5.000] | 0.99998 |
| seed43_B5_vs_calibrated_softheur_t095 | 5.714% | 6.429% | -0.714 pp | [-2.679, 1.250] | 0.22614 |
| seed43_B5_vs_learnedonly_t095 | 5.714% | 2.500% | 3.214 pp | [1.607, 4.911] | 0.99993 |
| seed42_B5_vs_learnedonly_t095 | 7.679% | 4.732% | 2.946 pp | [0.982, 4.911] | 0.99787 |

