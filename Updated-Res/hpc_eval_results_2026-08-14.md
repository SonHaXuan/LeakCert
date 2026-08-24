# LeakCert — HPC Evaluation Results (consolidated)

**Date:** 2026-08-14
**Server:** university HPC cluster (Slurm, L40S GPUs), repo `~/LeakCert`
**Result root:** `~/LeakCert/_run_results/`
**Units:** all certificate quantities in **nats** (natural log). `H(K) = ln(11566) = 9.356`.

> Scope: this file consolidates every completed evaluation on the two real fine-tuned
> targets. Numbers are copied verbatim from the JSON result files on the server; file
> paths are given per section for traceability.

---

## 1. Targets under test

| Target | Model | Corpus | Epochs | Canaries | Final loss | Checkpoint |
|---|---|---|---|---|---|---|
| **W1 Code-Small** | Qwen2.5-Coder-1.5B | 500K docs (`code_corpus.jsonl`) | 3 | 11,566 | 1.043 | `checkpoints/target_small/` |
| **Code-Mid** | Qwen2.5-Coder-7B | 700 docs (`cc_sub700.jsonl`) | 1 | 11,566 (panel injected) | 0.044 | `checkpoints/target_mid_sub2/checkpoint-20614/` |

Canary panel (both): 11,566 total — T1 literal ×10,000, T2 paraphrase ×1,000,
T3 semantic ×283, T4 vulnerability ×283.

---

## 2. Canary memorization — KL divergence (1.5B)

`D_KL(p_target ∥ p_ref)` per canary, target vs. base 1.5B reference.
Source: `hpc_paper_scale/certificate_sweep/certificate_sweep.json`.

| Canary type | n | Mean KL (nats) | Interpretation |
|---|---|---|---|
| **All** | 11,566 | **19.99** | Strong likelihood memorization |
| T1 literal | 10,000 | 17.53 | High |
| T2 paraphrase | 1,000 | 11.13 | High |
| T3 semantic | 283 | **156.46** | Extreme (distribution shift) |
| T4 vulnerability | 283 | **1.84** | Low — the only type below H(K) per-panel |

**Takeaway:** the target *did* memorize the canaries in the likelihood sense
(mean KL ≈ 20 nats ≫ H(K) = 9.356). T3 is off the charts; T4 is barely elevated.

---

## 3. Certificate — 1.5B (Table 1)

Source: `hpc_paper_scale/certificate/table1_certificate.json`.
Query-budget sweep B ∈ [100, 10^7]. Cert capped at H(K) = 9.356; entropy cap passes on
every row (`entropy_cap_pass: true`).

| B | Raw Hoeffding (nats) | Capped cert (nats) | Empirical MI (raw) | P(extract) | Vacuous |
|---:|---:|---:|---:|---:|:--:|
| 100 | 2,429.4 | 9.356 | 108.2 | 1.00 | yes |
| 1,000 | 24,294.1 | 9.356 | 1,082.0 | 1.00 | yes |
| 10,000 | 242,940.6 | 9.356 | 10,819.9 | 1.00 | yes |
| 100,000 | 2.43M | 9.356 | 108,199 | 1.00 | yes |
| 10,000,000 | 242.9M | 9.356 | 10.8M | 1.00 | yes |

**Result: certificate is VACUOUS at every tested budget** — raw Hoeffding ≫ H(K), so it
caps at H(K) and P(extract) ≤ 100%. All tested budgets are in the vacuous regime
(B ≥ B* = H(K)/C1). Tightness table (`table3_tightness.json`) reports ratio = 1.0 at every
B, i.e. cert = capped empirical MI = H(K) (both pinned to the cap — not a meaningful
tightness signal).

---

## 4. Certificate — 7B (Table 1)

Source: `hpc_eval_cert_mid/certificate/table1_certificate.json`. Runtime 7h 56m (job 1000858).

| B | Raw Hoeffding (nats) | Capped cert (nats) | Empirical MI (raw) | P(extract) | Vacuous |
|---:|---:|---:|---:|---:|:--:|
| 100 | 3,215.5 | 9.356 | 84.3 | 1.00 | yes |
| 1,000 | 32,155.2 | 9.356 | 842.6 | 1.00 | yes |
| 10,000 | 321,552.2 | 9.356 | 8,426.1 | 1.00 | yes |
| 10,000,000 | 321.6M | 9.356 | 8.4M | 1.00 | yes |

**Result: same shape as 1.5B — vacuous, capped at 9.356 nats, P(extract) ≤ 100%.**
The 7B raw MI proxy per query (84.3 @ B=100) is actually *lower* than 1.5B (108.2), but
both saturate the cap. Cert is **not tight** — expected, since the 7B target saw only
1 epoch on a 700-doc subset. Entropy cap passes all rows.

---

## 5. Small-budget certificate sweep (1.5B) — the only non-vacuous result

Source: `hpc_paper_scale/certificate_sweep/certificate_sweep.json` (job 948772, corrected
`vacuous` flag = raw uncapped Hoeffding vs H(K)).

Type-stratified with per-type entropy H = ln(283) = **5.6454** for the 283-item T3/T4 panels.
Only **T4 vulnerability at very small budgets** clears the cap:

| Type | B | Hoeffding cert (nats) | Bernstein (nats) | P(extract) | Vacuous |
|---|---:|---:|---:|---:|:--:|
| **T4** | 1 | **2.645** | 2.242 | **0.574** | **no** |
| **T4** | 2 | **5.291** | 4.485 | **0.972** | **no** |
| T4 | 5 | 5.645 (cap) | 5.645 | 1.00 | yes |
| T4 | ≥10 | 5.645 (cap) | — | 1.00 | yes |

All other types (and the full 11,566 panel) are vacuous even at B=1, because their mean KL
(17–156 nats) exceeds their entropy → B* < 1. **The story is type-stratified accounting:**
a genuine, non-trivial extraction-probability bound (57.4% at one query) exists only for the
low-memorization T4 sub-panel.

---

## 6. Prior sensitivity (Table 4) & DP comparison (Table 8) — 1.5B

`table4_prior.json`: uniform vs. type-empirical prior both cap at ~9.3–9.4 nats
(D_KL(prior∥uniform) ≈ 0) — prior choice does not change the (capped) headline.

`table8_dp_comparison.json`: LeakCert bound (capped 9.4 nats) vs analytic DP bound at
ε ∈ {1,2,4,8,16}. Raw DP bound grows 5,000 → 1.28M nats as ε increases; both cap at H(K),
ratio 1.0. Table 8 is analytic (no DP checkpoints were trained — deferred as impractical
and low-value given 0% verbatim extraction).

---

## 7. Attacks — W4 code-secret & W5 paraphrase (1.5B)

Source: `hpc_eval_attacks/w5/table6_paraphrase_robustness.json` (reduced panel, 25/type =
100 canaries; W4 = 700 prompts, W5 = 3,500 prompts). Defenses: B1 (none), B5 (content
filter), LEAKCERT.

| Defense | W4 rate | W4 95% CI | W5 rate | W5 95% CI |
|---|---:|---|---:|---|
| B1 no_defense | **0.00%** | [0, 0.55%] | **0.00%** | [0, 0.11%] |
| B5 content_filter | 0.00% | [0, 0.55%] | 0.00% | [0, 0.11%] |
| LEAKCERT | 0.00% | [0, 0.55%] | 0.00% | [0, 0.11%] |

W5 per-mode (template / language / regex-class / natural-language / base64-decode
variation): **all 0.00%** (700 each). Ratio W5/W4 = ∞ (0/0).

**Result: 0% verbatim extraction under every condition** — W4 templates, all 5 W5
paraphrase modes, against the undefended target. **Likelihood memorization ≠ verbatim
extractability at 1.5B.** The KL certificate flags leakage that extraction-rate auditing
entirely misses — a pro-certificate finding.

### 7a. W4 Table 2 — code-secret extraction, incl. A-adaptive attacker

Source: `hpc_eval_attacks/w4/table2_extraction.json` (job **1002479**, saved 2026-08-15 via
the incremental-save fix — see §10). Path A = W4 workload prompts (700, one query each);
Path B = A-adaptive UCB-bandit attacker at B=100 (100 canaries). B≥1000 omitted
(intractable on one L40S, ~48h+/pair, and stay 0%).

| Defense | Path A W4 workload | Path A 95% CI | Path B A-adaptive B=100 | Path B 95% CI |
|---|---:|---|---:|---|
| B1 no_defense | **0.00%** (0/700) | [0, 0.55%] | **0.00%** (0/100) | [0, 3.7%] |
| B5 content_filter | 0.00% (0/700) | [0, 0.55%] | 0.00% (0/100) | [0, 3.7%] |
| LEAKCERT | 0.00% (0/700) | [0, 0.55%] | 0.00% (0/100) | [0, 3.7%] |

**Result: 0% verbatim extraction across both the static W4 workload and the adaptive
attacker**, for every defense. The A-adaptive bandit — the framework's main attack — gains
nothing over the static templates: at ~1 query/canary it never recovers a secret verbatim.
This closes the last open extraction datapoint for the 1.5B target; every attack surface
(W4 static, W4 adaptive, W5 ×5 paraphrase modes, LRT) is now confirmed 0%.

---

## 8. LRT / MIA attack (Table 11) + false-positive control (1.5B)

Source: `hpc_eval_attacks/lrt/table11_lrt.json` and `..._fpcontrol.json`.
A-greedy-LRT, SPRT early-stop, members-only panel (100) vs. FP control (held-out
non-members, seed 999).

**Members panel — detection rate:**

| Defense | Overall | T1 | T2 | T3 | T4 | Mean queries | Verbatim |
|---|---:|---:|---:|---:|---:|---:|---:|
| B1 | 99% | 96 | 100 | 100 | 100 | 1.04 | 0% |
| B5 | 94% | 80 | 96 | 100 | 100 | 1.34 | 0% |
| LEAKCERT | 88% | 60 | 92 | 100 | 100 | 1.55 | 0% |

**FP control — non-members detected at nearly the same rate:**

| Defense | Overall (members) | Overall (non-members) |
|---|---:|---:|
| B1 | 99% | **100%** |
| B5 | 94% | **90%** |
| LEAKCERT | 88% | **93%** |

**Result: TPR ≈ FPR → the membership-detection claim is RETRACTED.** The completion-based
SPRT keys on "text is target-generated" (target is fine-tuned *from* the reference, so
Λ = log p_t − log p_r > 0 for *any* target generation), not on memorization. A valid MIA
must score the **secret's** likelihood ratio calibrated against non-members — which is
exactly what `KLEstimator`/the certificate already do. (LEAKCERT does still raise the T1
query cost — 60% at ~2.9 queries vs B1's 96% at ~1.1 — where its regex/hash mechanism
applies; T3 semantic passes every defense because distribution shift, not a string, is the
signal.)

---

## 9. Utility — W3 HumanEval pass@1 (1.5B)

Source: `hpc_eval_w3/w3/w3_utility.json`. 164 HumanEval problems, temp 0.2 / top-p 0.95,
executed in-container.

| Defense | pass@1 | n_correct / 164 | Notes |
|---|---:|---:|---|
| B1 no_defense | 6.1% | 10 | baseline |
| B2 temperature 0.5 | 4.3% | 7 | |
| B3 top-p 0.7 | 6.7% | 11 | |
| B5 content_filter | 4.3% | 7 | |
| **LEAKCERT** | **6.1%** | 10 | refusal rate **0.0%**, median latency 51.9s |

**Result: LEAKCERT matches the no-defense baseline (6.1%, 0% refusals)** — the defense
layer is not the utility bottleneck. Spread across defenses (4.3–6.7%) is sampling noise on
164 problems. (Absolute pass@1 is low because the target is a 1.5B base fine-tuned on a
canary-injected code corpus, not an instruction-tuned coder.)

---

## 10. Status matrix

| Evaluation | 1.5B (Code-Small) | 7B (Code-Mid) |
|---|---|---|
| Certificate (Table 1, KL, Thm 10/13/17) | ✅ | ✅ |
| Small-budget cert sweep | ✅ | ➖ not run |
| Prior (Table 4) / DP (Table 8) | ✅ (analytic DP) | ➖ |
| W5 paraphrase (Table 6) | ✅ (0%) | ❌ not run |
| W4 code-secret (Table 2) | ✅ **(0%, job 1002479)** | ❌ not run |
| LRT + FP control (Table 11) | ✅ (retracted) | ❌ not run |
| W3 utility (HumanEval) | ✅ | ❌ not run |

**Known gaps / next steps**
1. **W4 Table 2 — RESOLVED.** For prior runs the eval wrote `table2_extraction.json` only at
   the very end, and the intractable `adaptive_budgets: [100, 1000, 10000]` (~48h+ per pair at
   B≥1000) meant every run hit the 48h wall mid-sweep and discarded it. **Fixed 2026-08-14
   (commit `3fc31a5`):** incremental `_flush_table2()` saves after each stage + budgets trimmed
   to `[100]`. Job **1002479** still hit the 48h wall (in the *downstream* Table 11 LRT stage,
   which re-runs A-adaptive/A-LRT at full budget=10^4), **but the fix worked as intended: the
   complete W4 Table 2 was persisted to disk before the timeout** — see §7a. Remaining cleanup:
   split the full-budget LRT stage into its own short job so the sweep no longer wastes 48h
   re-deriving already-saved Table 11 data.
2. The **full 283/type W4** ("Target A") is heavier still (1,132 canaries) — even B=100 may
   exceed 48h; run as a shrunken panel or job array if a paper-scale W4 table is needed.
3. **The entire 7B attack (W4/W5/LRT) + utility (W3) suite is unrun** — only the 7B
   certificate exists. This is the open scientific question: *does the 7B target
   verbatim-leak where the 1.5B does not?* Needs a 7B attacks config + 7B W3 config pointing
   at `target_mid_sub2/checkpoint-20614`.

---

## 11. Headline narrative (five steps, both models)

1. **Memorized** — mean KL ≈ 20 nats (T3 up to 156); the target clearly encodes the canaries.
2. **Not verbatim-extractable** — 0% under W4 (static + A-adaptive bandit) and all W5
   paraphrase modes (CI upper ≤ 0.55%).
3. **The naïve MIA is a mirage** — LRT "detection" is TPR ≈ FPR; it detects
   target-generated text, not membership (claim retracted under FP control).
4. **The certificate bounds the right quantity** — the KL-based bound (what a *valid* MIA
   would score) is what carries information; type-stratified, only T4 at B ≤ 2 is
   non-vacuous, everything else caps at H(K).
5. **Defense helps where a mechanism applies** — LEAKCERT raises T1 query cost (regex/hash),
   preserves utility (W3 pass@1 = baseline, 0% refusals), but cannot touch T3 semantic
   leakage (distribution shift, not a string).

---

## 12. Caveats

- Certificate is **vacuous at all practical budgets** for the full panel (both models);
  the meaningful bound exists only for the T4 sub-panel at B ∈ {1,2}. **Do not make
  headline certificate-tightness claims.**
- Tightness "ratio = 1.0" in Table 3 reflects both cert and empirical MI pinned to the
  H(K) cap — not genuine tightness.
- 7B is a 1-epoch / 700-doc scaled demo, not paper-scale training; its certificate is
  expected to be loose.
- W3 absolute pass@1 is low by design (non-instruction-tuned 1.5B base).
- DP (Table 8) is analytic; no per-ε DP checkpoints were trained.
</content>
