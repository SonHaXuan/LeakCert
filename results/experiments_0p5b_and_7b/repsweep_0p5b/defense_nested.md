# Nested tune-freeze-evaluate defense evaluation on the 0.5B repetition-sweep models

Protocol: the member panel (1,132 canaries) is split by canary unit into disjoint parts A=460 (train the refusal classifier), B=240 (choose the threshold, together with the tune half of HumanEval) and C=432 (evaluate only). The threshold is the grid value (0.5, 0.7, 0.8, 0.9, 0.95, 0.99) with the lowest B-extraction among those with refusal <= 2.5% on the HumanEval tune half; ties are broken toward the larger threshold. It is then frozen. Resampling is by canary unit (339 units in C; a T2 canary stays with its T1 source), 10,000 resamples. Completions are generated once per model and each defense is applied as a stateless filter, so the comparison is paired (2 repeats, 64 new tokens). B5 is the regex bank; "learned-only" is the refusal stage alone.

Models: the repetition-sweep runs r16, r64, r128 and r256 (R = 16, 64, 128, 256). Raw files: `raw/<run>/defense_nested/nested_summary.json`.

## Frozen threshold

| Run | Frozen t | Refusal on HumanEval tune half | Selection grid (t: tune refusal / B W5 extraction %) |
|---|---|---|---|
| r16 | 0.7 | 1.2% | 0.5: 24.4% / 0.17; 0.7: 1.2% / 0.40; >=0.8: 0% / 0.44 |
| r64 | 0.7 | 1.2% | 0.5: 39.0% / 0.35; 0.7: 1.2% / 0.75; >=0.8: 0% / 0.77 |
| r128 | 0.99 | 0.0% | 0.5: 45.1% / 0.56; 0.7: 9.8% / 1.00; >=0.8: 0% / 1.02 |
| r256 | 0.99 | 0.0% | 0.5: 45.1% / 0.52; 0.7: 1.2% / 1.04; >=0.8: 0% / 1.04 |

For r128 every threshold from 0.8 up gives the same B-extraction (1.02%) and 0% refusal on the tune half, so the tie-break selects 0.99. For r256 the same holds for every threshold from 0.7 up (B-extraction 1.04%).

## Extraction on part C (%), by defense

| Run | Workload | Prompts | B1 none | B5 filter | Learned-only | B5 minus learned-only (pp) [95% canary-level CI] | P(B5 > ours) | Refusal on C prompts |
|---|---|---|---|---|---|---|---|---|
| r16 | W4 | 6,048 | 2.60 | 2.60 | 2.53 | 0.066 [0.016, 0.140] | 0.984 | 16.6% |
| r16 | W5 | 8,640 | 0.47 | 0.46 | 0.42 | 0.046 [0.011, 0.098] | 0.982 | 16.1% |
| r64 | W4 | 6,048 | 3.22 | 3.21 | 3.19 | 0.017 [0.000, 0.053] | 0.632 | 14.9% |
| r64 | W5 | 8,640 | 0.79 | 0.79 | 0.78 | 0.012 [0.000, 0.037] | 0.639 | 13.9% |
| r128 | W4 | 6,048 | 4.00 | 3.95 | 3.97 | -0.017 [-0.052, 0.000] | 0.000 | 10.3% |
| r128 | W5 | 8,640 | 0.95 | 0.95 | 0.95 | 0.000 [0.000, 0.000] | 0.000 | 8.7% |
| r256 | W4 | 6,048 | 3.69 | 3.64 | 3.64 | 0.000 [-0.049, 0.049] | 0.348 | 9.7% |
| r256 | W5 | 8,640 | 1.15 | 1.11 | 1.11 | 0.000 [0.000, 0.000] | 0.000 | 7.8% |

Per type (W4): r64 T4 12.26 / 12.26 / 12.20 (B1 / B5 / learned-only), T1 0.06 / 0.00 / 0.00; r128 T4 15.11 / 15.11 / 15.11, T1 0.18 / 0.00 / 0.06; r256 T4 13.91 / 13.84 / 13.84, T1 0.18 / 0.06 / 0.06; T2 and T3 are 0 for every defense. r16 shows the same pattern (T4 9.92 / 9.92 / 9.67). For W5, T4 is 3.63 (r128) and 4.25 (r256) for all three arms.

The prompt-level bootstrap gives almost the same intervals (for example r16 W5 [0.01, 0.09] versus canary-level [0.011, 0.098]) because hits are spread over many canaries.

## Reading

- Out of sample, the learned-only refusal removes at most 0.07 percentage points of extraction relative to B5 (r16 W4), 0.01 to 0.02 points on r64, and nothing on r128 and r256 (identical rates on W5; on W4 the learned-only rate is 0.017 points above B5 for r128 and equal to B5 for r256).
- Both defenses leave extraction almost equal to no defense (B1). All measured extraction is T4 vulnerability idioms; T1 to T3 are 0 (single T1 hits under B1 on r64, r128 and r256 W4 are filtered by B5).
- Power is low: undefended extraction is only 0.5% to 4.0% (W4) and 0.5% to 1.2% (W5), so absolute differences are bounded by the baseline.
- The refusal rate on part C prompts is 8% to 17%, versus 0% to 1.2% on legitimate HumanEval completions at the frozen threshold: the classifier fires on the canary-prompt completions, which resemble its training positives.
- Lower thresholds remove more extraction (t=0.5 roughly halves B-extraction) but refuse 24% to 45% of legitimate HumanEval completions.

Limits: HumanEval has 164 problems, so each half has 82 and the tune refusal rate (1.2% = one problem) is coarse; one model per run, two repeats, one split seed; classifier positives come from part A's own canaries and hit completions, so positives are few when extraction is rare.
