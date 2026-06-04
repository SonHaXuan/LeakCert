# Updated Results Package

Generated: `2026-06-04T09:25:34+0700`

Source commit at package generation: `2df352c575f8c5cf86bb79488709029f46c6bdde`

This folder is a sanitized result bundle for writing and auditing. It intentionally excludes:

- local secret files such as `.env` and `*.pem`
- model checkpoints and large model/tokenizer files
- local paper PDF/source and venue/timeline metadata
- raw private data or author/user-level artifacts

## Highest-Signal Findings

1. **W5 leakage reduction is the strongest current empirical result.**
   The learned-only refusal setting at threshold `0.95` reduces W5 extraction below the B5 content-filter baseline on both seed42 and seed43. The 1M-sample bootstrap comparison gives strong evidence for the reduction.

2. **The original uncalibrated LEAKCERT setting is not the best headline result.**
   Cross-seed W5 means show original LEAKCERT does not consistently beat B5. The improved learned-only refusal variant is the result worth discussing.

3. **W3 utility weakness is model/checkpoint-driven, not defense-driven.**
   On the W3-164 diagnostic, B1, B5, and LEAKCERT all achieve `10.98%` pass@1. LEAKCERT refusal is only `0.61%`, so the defense layer is not the main cause of low utility in this setting.

4. **LCCT full training-data extraction cannot be reproduced paper-grade from public artifacts.**
   The LCCT authors confirmed the forbidden-question CSV is exact, but declined release of user-level extraction artifacts due privacy. The correct path is a comparable reimplementation with explicit limitation.

5. **Certificate results are currently diagnostic, not headline.**
   Existing certificate runs remain vacuous/non-competitive. A non-vacuous certificate claim still needs improved calibration/checkpoints and likely server/GPU follow-up.

## Best Numbers To Reuse

### Learned-only W5 evidence

| setting | W4 | W5 | note |
|---|---:|---:|---|
| learned-only t=0.95 seed43 | 4.91% | 2.50% | strongest W5 reduction |
| learned-only t=0.95 seed42 | 7.59% | 4.73% | replicated W5 reduction |

Bootstrap comparisons:

| comparison | baseline-method | 95% CI | P(baseline > method) |
|---|---:|---:|---:|
| seed43 B5 vs learned-only t=0.95 | 3.214 pp | [1.607, 4.911] | 0.99993 |
| seed42 B5 vs learned-only t=0.95 | 2.946 pp | [0.982, 4.911] | 0.99787 |

### W3 utility diagnostic

| defense | pass@1 | refusal |
|---|---:|---:|
| B1 no defense | 10.98% | 0.00% |
| B5 content filter | 10.98% | 0.00% |
| LEAKCERT learned-only t=0.95 | 10.98% | 0.61% |

## Bottom Line

The current package supports a careful small-scale/positive-control claim: learned refusal/accounting can reduce extraction in W4/W5-style settings with minimal additional W3 refusal. It does **not** yet support full-scale claims about DP sweeps, multi-model evaluation, non-vacuous certificates, or full LCCT training-data extraction.
