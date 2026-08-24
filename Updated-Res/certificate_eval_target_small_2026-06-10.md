# LeakCert Certificate Evaluation — W1 Code-Small Target

**Run:** Slurm job `944189` on a university HPC cluster (node `a256-t4-04`, T4 GPU, Singularity `pytorch_25.09.sif`)
**Date:** 2026-06-10 (eval), target trained by job `940383` (2026-06-08→10, 3 epochs, 45h17m)
**Config:** `experiments/configs/hpc_paper_scale.yaml`
**Target model:** `checkpoints/target_small` (Qwen2.5-Coder-1.5B, fine-tuned on 500k-doc corpus with 11,566 injected canaries)
**Reference model:** `models/qwen2.5-coder-1.5b` (base, un-fine-tuned)
**Raw outputs:** `_run_results/hpc_paper_scale/certificate/{kl_estimates,table1_certificate,table3_tightness,table4_prior,table8_dp_comparison}.json`

All quantities are in **nats** (natural log).

---

## 1. KL estimates — per-canary memorization (D_KL(p_target ∥ p_ref))

The model **clearly memorized** the injected canaries: the fine-tuned target assigns far higher
probability to the secrets than the base reference model.

| Statistic | Value (nats) |
|---|---|
| n_canaries | 11,566 |
| mean | 19.99 |
| median | 9.45 |
| std | 29.52 |
| min | 0.00 |
| max | 284.08 |

### By canary type
| Type | n | mean KL | max KL | Reading |
|---|---|---|---|---|
| **T1** literal | 10,000 | 17.53 | 64.12 | strong memorization |
| **T2** paraphrase | 1,000 | 11.13 | 44.14 | moderate |
| **T3** semantic | 283 | **156.46** | **284.08** | extreme memorization |
| **T4** vulnerability | 283 | 1.84 | 8.29 | barely memorized |

**Takeaway:** literal (T1) and especially semantic (T3) canaries are memorized very strongly;
vulnerability canaries (T4) are nearly absent from memory. This is a real, interpretable signal that
the training pipeline injected and the model retained the secrets as intended.

---

## 2. Certificate bounds (Theorems 10 / 13) — Table 1

For each query budget B, the Hoeffding/Bernstein extractable-information bound. The **raw** bound is
the theorem value; the **capped** bound applies the information ceiling H(K) = ln(11,566) ≈ **9.356 nats**
(no attacker can extract more than the prior entropy of the canary set).

| B | raw Hoeffding (nats) | capped cert (nats) | P(extract) ≤ | vacuous? |
|---:|---:|---:|---:|:--:|
| 100 | 2,429 | 9.356 | 1.0 | yes |
| 1,000 | 24,294 | 9.356 | 1.0 | yes |
| 5,000 | 121,470 | 9.356 | 1.0 | yes |
| 10,000 | 242,941 | 9.356 | 1.0 | yes |
| 50,000 | 1.21e6 | 9.356 | 1.0 | yes |
| 100,000 | 2.43e6 | 9.356 | 1.0 | yes |
| 1,000,000 | 2.43e7 | 9.356 | 1.0 | yes |
| 10,000,000 | 2.43e8 | 9.356 | 1.0 | yes |

**Takeaway — the certificate is VACUOUS for the undefended model at every budget.** Because
memorization is strong (mean KL ≈ 20 nats), the raw bound vastly exceeds the H(K) = 9.356-nat ceiling
and is clipped to it, giving an extraction-probability bound of 1.0. In plain terms: **without a
defense, we cannot certify that the secrets are non-extractable.** This is the expected, honest result
and is precisely the motivation for the LeakCert runtime monitor (certificate-budget throttle +
rate-limit + uncertainty-refusal + target-string suppression), which lowers the effective query budget
and KL so the bound can become non-vacuous.

---

## 3. Tightness (Table 3)
At every budget the capped certificate equals the (capped) empirical MI → ratio = 1.0, `tight = true`.
This tightness is trivial here: both quantities sit at the H(K) cap. Tightness becomes informative only
once the bound drops below the ceiling (i.e. under the defense).

## 4. Prior misspecification (Table 4, Theorem 7)
| Prior | H(K) | capped cert (nats) |
|---|---:|---:|
| uniform | 9.356 | 9.4 |
| type-empirical | 9.250 | 9.3 |
Switching from a uniform to the type-empirical prior changes H(K) only marginally (9.36 → 9.25 nats);
both remain at the cap.

## 5. DP comparison (Table 8)
| DP ε | LeakCert (nats) | raw DP bound (nats) | capped DP bound |
|---:|---:|---:|---:|
| 1 | 9.4 | 5,000 | 9.4 |
| 2 | 9.4 | 20,000 | 9.4 |
| 4 | 9.4 | 80,000 | 9.4 |
| 8 | 9.4 | 320,000 | 9.4 |
| 16 | 9.4 | 1.28e6 | 9.4 |
Both LeakCert and the DP composition bound (B·ε²/2) exceed H(K) and clip to it — neither certifies the
undefended model. (Meaningful separation between them is expected only at smaller budgets / under the
defended query stream.)

---

## Conclusion
1. **Training succeeded:** the W1 Code-Small target memorized the injected canaries with a clear,
   type-dependent signal (T3 ≫ T1 > T2 ≫ T4).
2. **Undefended certificate is vacuous:** at all query budgets the bound caps at H(K) ≈ 9.36 nats and
   P(extract) ≤ 1.0 — no non-extraction guarantee without a defense.
3. **Next:** re-run the certificate over the *defended* query stream (runtime monitor B6 / DP checkpoints)
   and the attack workloads (W4 code-secret, W5 paraphrase) to show where the bound becomes non-vacuous.

## Reproduce
```bash
# on the HPC cluster, in ~/LeakCert
sbatch slurm/eval_certificate.sbatch
# → _run_results/hpc_paper_scale/certificate/*.json
```
