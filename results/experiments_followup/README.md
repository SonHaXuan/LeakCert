# Follow-up measurements (synthetic canaries only)

Summary JSON files from additional measurements on the Qwen2.5-Coder-0.5B repetition sweep, a 1.5B reference, a 7B target and a mixed-repetition model. Per-prompt completions, per-canary row dumps and code are not included. Timestamps and host fields were removed from the metadata.

| Folder | Content |
|---|---|
| `A1_extraction_prefix/` | Prefix/context coverage and extraction check at R=64/128/256 (`summary.json`, `context_coverage.json`, `panel_info.json`) |
| `A2_panel_overlap/` | Overlap between member and non-member panels (secret strings per type and T4 subtype) |
| `A345_config/` | Corpus composition of the repetition sweep |
| `B1_mixed_r/` | One model trained on a corpus with canary groups at R = 1, 4, 16, 32, 64 (two training seeds): AUC and mean LLR per group and type, bootstrap CIs |
| `B2_td_1p5b/` | 1.5B target: same-template and template-disjoint exposure AUC (matched and base reference) |
| `B3_7b_w4w5/` | 7B target, static (W4) and paraphrase (W5) prompts per canary type for member, non-member and template-disjoint panels |
| `B4_nonmember_seed1000/` | Second non-member seed (1000) against seed 999 at R=1/64/128 |
| `X2_seed43/` | Second training seed (43) for R=16 and R=64: exposure AUC, same-template and template-disjoint |
| `V_checks/` | Offline consistency checks of reported numbers |

Headline numbers (exposure LLR, matched no-canary reference, 283 canaries per type):

| R | Seed | AUC same-template | AUC template-disjoint |
|---|---|---|---|
| 16 | 42 | 0.552 | 0.965 |
| 16 | 43 | 0.553 | 0.969 |
| 64 | 42 | 0.788 | 0.997 |
| 64 | 43 | 0.789 | 0.998 |

Per-type AUC differs by at most 0.018 between the two training seeds. All canaries are synthetic strings generated for this study; no real credentials are involved.
