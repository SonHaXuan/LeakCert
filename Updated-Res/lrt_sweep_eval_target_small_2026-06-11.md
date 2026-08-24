# LRT Attack + Small-Budget Certificate Sweep — W1 Code-Small Target

**Run:** Slurm job `945795` on a university HPC cluster (node `i256-a10-07`, a10 GPU, 19 min)
**Date:** 2026-06-11
**Target:** `checkpoints/target_small` (Qwen2.5-Coder-1.5B + 11,566 canaries; trained job 940383)
**Inputs:** KL estimates from the certificate eval (job 944189); eval panel 25/type × 4 = 100 canaries
**Scripts:** `experiments/run_certificate_sweep.py`, `experiments/run_lrt_attack.py` (via `slurm/eval_lrt_sweep.sbatch`)
**Artifacts:** `Updated-Res/artifacts/lrt_sweep_target_small_2026-06-11/{certificate_sweep,table11_lrt}.json`

These two experiments close the loop opened by the W4/W5 result (0% verbatim extraction despite
mean KL ≈ 20 nats — see `attack_eval_target_small_2026-06-10.md`).

---

## 1. Small-budget certificate sweep — first NON-VACUOUS certificate

Reuses the full-panel per-canary KL estimates; recomputes Theorem 10/13 bounds at B ∈ {1…1000},
for the full panel and per-type sub-panels (each with its own H(K) = ln(n_type)).

**Full panel (11,566 canaries, H(K)=9.356):** vacuous at *every* budget down to **B=1**
(raw bound 24.3 nats at B=1 already exceeds H(K), since mean KL ≈ 20 ≳ H(K)). For this strongly
memorized panel, B* < 1 — no query budget yields a non-trivial guarantee for the undefended model.

**Per-type sub-panels:**

| Panel | n | mean KL | H(K) | B=1 | B=2 | B≥5 |
|---|---|---|---|---|---|---|
| T1 literal | 10,000 | 17.53 | 9.210 | at cap | at cap | at cap |
| T2 paraphrase | 1,000 | 11.13 | 6.908 | at cap | at cap | at cap |
| T3 semantic | 283 | 156.46 | 5.645 | at cap | at cap | at cap |
| **T4 vulnerability** | 283 | **1.84** | 5.645 | **2.645 nats, P(extract) ≤ 0.574** | **5.290, P ≤ 0.972** | at cap |

**Headline: the T4 panel is genuinely non-vacuous at B ≤ 2.** A one-query attacker provably extracts a
T4 canary with probability ≤ 57.4% (vs the trivial bound of 1). The crossover matches theory:
B* ≈ H(K)/C₁ = 5.645/1.84 ≈ 3. The certificate becomes informative exactly where memorization is
weak — **type-stratified certificate accounting matters**.

*Resolved (2026-06-16, job 948772, commit `f56e8dc`):* the earlier `vacuous`-flag float artifact is
fixed. Vacuity is now judged on the **raw (uncapped)** Hoeffding certificate vs H(K), not the capped
value vs `math.log(K)`, so capped T1–T3 rows no longer spuriously read non-vacuous. The corrected
`certificate_sweep.json` flags exactly **T4 at B∈{1,2}** as non-vacuous (2.645 / 5.290 nats < H=5.645)
and nothing else — which satisfies the Quality-Evidence Target B gate (every value ≤ H(K); ≥1 real
setting with 0 < cert < H(K)).

---

## 2. A-greedy-LRT attack (Table 11, LRT-only) — the KL signal IS attackable

SPRT likelihood-ratio attacker (Theorem 17 construct: generation goes through the defense under
test; per-query LLR uses raw target/ref log-probs). 100 canaries, ≤20 queries each, temperature 1.0.
"Detection" = SPRT accepts H₁ (canary present) — a membership-inference success, not extraction.

| Defense | Detection | Verbatim | Mean queries | T1 | T2 | T3 | T4 |
|---|---|---|---|---|---|---|---|
| B1 no_defense | **99%** | 0% | 1.04 | 96% | 100% | 100% | 100% |
| B5 content_filter | 94% | 0% | 1.34 | 80% | 96% | 100% | 100% |
| **LEAKCERT** | **88%** | 0% | 1.55 | **60%** | 92% | 100% | 100% |

Findings:
1. **Membership detection is near-instant against the undefended model** (99% in ~1 query): the
   likelihood leakage measured by the certificate is exploitable by a real attacker — just as
   membership inference, not verbatim extraction. Verbatim remains 0% under every defense,
   consistent with all W4/W5 results.
2. **LEAKCERT is the strongest defense against the LRT**, and the per-type split shows the
   mechanism: on T1 literal canaries (the regex+hash suppression target) detection falls
   96% → 60% and the attacker needs ~2.9 queries instead of ~1. B5's regex filter only reaches 80%.
3. **T3 semantic canaries defeat every defense** (100% detection): their KL is so extreme
   (~156 nats/query) that a single emitted completion decides the SPRT. Suppressing
   literal strings cannot help when the *distribution shift itself* is the signal.

### ⚠️ FP control (job 946249) — RETRACTS the membership-detection claim

A false-positive control was run on **held-out non-member canaries** (panel regenerated with
seed=999 — canaries the target never trained on; `--nonmember-seed 999`). If "detection" were a real
membership signal, it should be near-zero on non-members. It is not:

| Defense | Detection on MEMBERS | Detection on NON-MEMBERS (FPR) |
|---|---|---|
| B1 no_defense | 99% | **100%** |
| B5 content_filter | 94% | 90% |
| LEAKCERT | 88% | 93% |

**TPR ≈ FPR ≈ 90–100% → the LRT "detection rate" does NOT discriminate members from non-members,
so it is not evidence of membership inference.** Root cause: the SPRT here scores *self-generated
completions* with Λ = log p_target − log p_ref. Since the target is fine-tuned **from** the reference
and the completion is produced **by** the target, Λ > 0 for almost any target generation regardless of
membership — the test detects "text came from the fine-tuned model," not "this canary was memorized."

What survives: **verbatim rate is 0% on members and non-members alike** (consistent with all other
runs), and the **per-defense query cost** still shows LEAKCERT forcing ~3 queries on T1 vs ~1 (its
suppression is active). A valid membership attack must instead score the **secret's** likelihood ratio
(as the KL estimator does, log p_target(secret|ctx) − log p_ref(secret|ctx)) and be calibrated against
this non-member panel — that is the corrected follow-up, not the completion-based SPRT.

---

## Combined narrative (certificate + W4/W5 + LRT + sweep)

1. The target **memorizes** the canaries (mean KL ≈ 20 nats; certificate vacuous for the full panel).
2. The memorization is **not verbatim-extractable** (0% across W4/W5/adaptive/LRT, greedy and sampled,
   members and non-members).
3. The **completion-based SPRT does NOT yield a valid membership signal** (FP control: TPR≈FPR≈100%).
   A membership attack must score the *secret's* likelihood ratio and be calibrated vs non-members;
   the KL certificate already operates on exactly that secret-likelihood quantity.
4. The **certificate is the right abstraction**: it bounds extractable information (not strings) and
   becomes non-vacuous precisely where memorization is weak (T4, B ≤ 2).
5. The **runtime defense measurably raises attacker cost** where its mechanisms apply (T1: ~1 → ~3
   queries under LEAKCERT) — motivating KL-budget throttling (certificate accounting) over content
   filtering as the load-bearing defense layer.

## Reproduce
```bash
# on the HPC cluster, in ~/LeakCert (needs kl_estimates.json from eval_certificate.sbatch)
sbatch slurm/eval_lrt_sweep.sbatch
# → _run_results/hpc_paper_scale/certificate_sweep/certificate_sweep.json
# → _run_results/hpc_eval_attacks/lrt/{table11_lrt.json,lrt_audit.jsonl}
```
