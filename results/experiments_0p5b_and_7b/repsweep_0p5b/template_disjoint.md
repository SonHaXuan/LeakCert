# Template-disjoint non-member panel on the 0.5B repetition sweep

Non-members are generated with held-out templates (seed 999): new T1 contexts and secret formats, new T2 wrappers, new T3 layouts and new T4 insecure patterns. Members are the same seed-42 panel as in `exposure_and_sprt.md`. Raw files: `raw/<run>/c1_td/c1_summary_{nocanary,base}.json` and `raw/<run>/lrt_run/lrt/table11_lrt_fpcontrol_td.json`.

## Exposure: member vs non-member AUC (matched no-canary reference)

| R | Same-template non-members | Template-disjoint non-members | Mean LLR of non-members (same / disjoint) |
|---|---|---|---|
| 1 | 0.492 | 0.956 | 72.0 / 2.0 |
| 4 | 0.502 | 0.960 | 103.2 / 3.3 |
| 16 | 0.552 | 0.965 | 104.5 / 3.9 |
| 64 | 0.788 | 0.997 | 31.9 / -2.5 |
| 128 | 0.813 | 0.997 | 13.7 / -4.5 |

With the base reference the template-disjoint AUC is 0.876, 0.919, 0.940, 0.986, 0.982 for R = 1, 4, 16, 64, 128.

## SPRT detection rate (%): members / same-template non-members / template-disjoint non-members

| R | B1 no defense | B5 content filter | LeakCert |
|---|---|---|---|
| 1 | 100.0 / 99.0 / 98.5 | 96.0 / 97.5 / 98.0 | 95.0 / 96.5 / 98.5 |
| 4 | 99.5 / 100.0 / 99.0 | 91.0 / 89.5 / 96.5 | 86.5 / 88.0 / 95.0 |
| 16 | 100.0 / 100.0 / 98.5 | 86.0 / 85.5 / 95.5 | 81.0 / 82.5 / 91.0 |
| 64 | 99.5 / 100.0 / 99.5 | 84.0 / 83.5 / 93.5 | 86.0 / 83.5 / 91.5 |
| 128 | 99.5 / 97.0 / 100.0 | 83.0 / 83.0 / 90.5 | 80.5 / 81.5 / 90.5 |

## Reading

- Non-members that share templates with the members get a mean LLR of 72 to 105 for R <= 16 (14 to 32 at R=64 and R=128), whereas non-members with unseen templates get -5 to 4. The model learned the template format, so same-template non-members look like members.
- The template-disjoint AUC (0.96 at R=1) separates "template seen in training" from "template unseen"; it is not a per-canary membership AUC. The valid control for membership is the same-template non-member panel.
- The template hypothesis does not explain the SPRT result. On template-disjoint non-members the detection rate is still 90.5% to 100.0%, equal to or higher than on members at every R. The SPRT hit rate does not depend on membership or on template familiarity.

Limits: one run per R, one non-member seed, 200 canaries per SPRT panel; the held-out T4 patterns are different vulnerabilities, so they also differ in difficulty from the member patterns.
