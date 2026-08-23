# B1 — Extraction-rate CI recompute: per-request vs. per-canary estimand

**Status:** recovered/rewritten 2026-08-23 (original file referenced by the tracker was lost —
see `A_theory_corrections_draft.md` header for the same data-loss note; this version is
regrounded directly in `Updated-Res/aau_hpc_eval_results_2026-08-14.md` §7 and recomputed with
`compute_cp_ci.awk`, included alongside this file).

## 1. The problem

The paper reports 0% verbatim extraction on the W4/W5 workloads with 95% confidence intervals of
**[0, 0.55%]** (W4) and **[0, 0.11%]** (W5) — see `Updated-Res/aau_hpc_eval_results_2026-08-14.md`
lines 124-128. Both are exact Clopper-Pearson upper bounds for **zero hits**, but computed with
the number of *queries* as the trial count:

- W4: 0/700 queries → n=700
- W5: 0/3500 queries → n=3500

That is the correct CI for the estimand *"probability that a single extraction query, drawn at
random from the workload, returns a verbatim secret."* It is **not** the correct CI for the
estimand the paper's prose actually argues — *"probability that a given secret is extractable at
all"* — because the panel underlying both denominators is only **100 distinct canaries**. W4 fires
7 queries/canary (700/100) and W5 fires 35 queries/canary (3500/100); those repeated queries
against the same canary are not 700 (or 3500) independent Bernoulli draws over independent secrets
— they are ≤100 independent secrets, each probed several different ways. Reporting the CI as if
n=700/3500 silently treats "asked more ways" as "more independent evidence about more secrets,"
which understates the true uncertainty about **per-secret** extractability.

## 2. Two estimands, stated explicitly

| Estimand | What it answers | Trial count | Source counts |
|---|---|---:|---|
| **Per-request** | "If I fire one random extraction query, how often does it leak?" | n = queries (700 / 3500) | 0/700, 0/3500 |
| **Per-canary** | "Of the secrets in the panel, how many are extractable under this workload?" | n = distinct canaries (100) | 0/100 |

The per-canary estimand is the conservative, scientifically load-bearing one for the paper's claim
("the target does not leak its secrets") — it should be the number quoted in the headline, with
the per-request number kept as a secondary, weaker statistic.

## 3. Recomputed exact Clopper-Pearson 95% CIs

Computed with `compute_cp_ci.awk` (bisection on the exact binomial CDF, no incomplete-beta
dependency; included in this directory). Verified against the closed form for zero hits,
`upper = 1 - (alpha/2)^(1/n)`:

```
$ awk -f compute_cp_ci.awk -v x=0 -v n=700
x=0 n=700 alpha=0.050  point=0.000000%  CI=[0.000000%, 0.525597%]

$ awk -f compute_cp_ci.awk -v x=0 -v n=3500
x=0 n=3500 alpha=0.050  point=0.000000%  CI=[0.000000%, 0.105341%]

$ awk -f compute_cp_ci.awk -v x=0 -v n=100
x=0 n=100 alpha=0.050  point=0.000000%  CI=[0.000000%, 3.621669%]
```

| Estimand | Hits | n | 95% CI upper (exact) | Paper's current quoted figure |
|---|---:|---:|---:|---:|
| Per-request, W4 | 0 | 700 | **0.526%** | 0.55% |
| Per-request, W5 | 0 | 3500 | **0.105%** | 0.11% |
| **Per-canary (both workloads)** | 0 | 100 | **3.622%** | *(not currently reported anywhere)* |

The per-request numbers match the paper's quoted 0.55%/0.11% to within rounding (the paper's
figures round the exact 0.526%/0.105% up to 2 significant digits — consistent, not an error in
those two cells). The gap is the **missing third row**: nowhere does the paper report the 3.62%
per-canary bound, which is 6.5x (vs. W4's 0.55%) to 34x (vs. W5's 0.11%) larger. Also matches the
`aau_hpc_eval_results_2026-08-14.md` line 147-149 "Path B" A-adaptive row (0/100, CI already listed
there as "[0, 3.7%]" — our exact value 3.622% rounds to that 3.7%, confirming this bound was
already computed once for the adaptive-attack table but never carried over to the W4/W5 headline
table using the same n=100 denominator).

## 4. What to change

1. Wherever the manuscript cites **"[0, 0.55%]"** (W4) or **"[0, 0.11%]"** (W5) as *the* extraction
   bound, keep the number but relabel it explicitly as the **per-request** CI, and add the
   **per-canary CI of [0, 3.62%]** alongside it as the estimand that bounds "is any given secret
   extractable."
2. The 0.55%/0.11% numbers are not wrong — they answer a real (if weaker) question — but presenting
   them alone, without the 3.62% figure, understates the paper's own uncertainty about per-secret
   extractability by 6-34x. Both should be reported side by side (see table in §3).
3. The `.tex` manuscript source is not present in this repository (same gap noted for A2/A4/A7 in
   `A_theory_corrections_draft.md`) — this correction must be applied wherever that source lives;
   it cannot be patched from this checkout.

## 5. Reproduce

```bash
cd ndss2027_resubmit/results
awk -f compute_cp_ci.awk -v x=0 -v n=700     # W4 per-request
awk -f compute_cp_ci.awk -v x=0 -v n=3500    # W5 per-request
awk -f compute_cp_ci.awk -v x=0 -v n=100     # per-canary (either workload)
awk -f compute_cp_ci.awk -v x=1 -v n=142632  # general x>0 case, see B2_sampled_hit_report.md
```

Source counts: `Updated-Res/aau_hpc_eval_results_2026-08-14.md` §7 ("W4 code-secret & W5
paraphrase (1.5B)"), cross-checked against the A-adaptive Path B row (§7a) which already uses the
n=100 per-canary denominator for its own CI.
