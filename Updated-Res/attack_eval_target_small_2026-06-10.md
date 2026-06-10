# LeakCert W4/W5 Attack-Workload Evaluation — W1 Code-Small Target (temperature = 1.0)

**Run:** Slurm job `944415` on AAU AI Cloud (node `i256-a10-07`, a10 GPU, Singularity `pytorch_25.09.sif`)
**Date:** 2026-06-10
**Config:** `experiments/configs/aau_eval_attacks.yaml` (eval panel 25/type × 4 = 100 canaries, subset of the 11,566 injected)
**Target:** `checkpoints/target_small` (Qwen2.5-Coder-1.5B, 500k-doc + 11,566 canaries)
**Reference:** `models/qwen2.5-coder-1.5b`
**Decoding:** temperature **1.0 (sampling)**, max_new_tokens 128
**Status:** W5 complete; W4 Path A complete; W4 Path B (adaptive) cancelled (impractically slow — see below).

---

## Headline result: ~0% verbatim extraction across all defenses

Despite the certificate showing **strong latent memorization** (mean KL ≈ 20 nats; T3 semantic ≈ 156),
the target **does not regurgitate the canaries verbatim** under single-query extraction at temperature 1.0.

### W5 Table 6 — paraphrase robustness (W5/W4 ratio)
| Defence | W4 rate | W5 rate | Ratio |
|---|---|---|---|
| B1 no_defense | 0.00% (0/700) | 0.03% (1/3500) | ∞ (0/0) |
| B5 content_filter | 0.00% (0/700) | 0.00% (0/3500) | ∞ |
| LEAKCERT | 0.00% (0/700) | 0.00% (0/3500) | ∞ |

The single W5 hit (1/12,600 audit rows total) was a `natural_language` paraphrase under B1 — statistically noise.

### W4 Path A — one-query templates (budget-independent)
| Defence | W4 extraction rate |
|---|---|
| B1 no_defense | 0.00% (0/700) |
| B5 content_filter | 0.00% (0/700) |
| LEAKCERT | 0.00% (0/700) |

### W4 Path B — A-adaptive attacker (CANCELLED)
The adaptive attacker issues many model calls per budget unit: the first run (B=100, B1) had not
completed after ~35 min of active GPU compute. Extrapolated, B=1,000 / B=10,000 across 3 defenses
(+ the LRT table at B=10⁴) would exceed the 12h wall-clock limit. Given Path A and W5 already show a
0% baseline, Path B was cancelled rather than burn a day confirming 0%.

---

## Interpretation
1. **Latent memorization ≠ verbatim extractability.** High D_KL means the target assigns elevated
   probability to the secrets, but a single temperature-1.0 sample essentially never reproduces a random
   literal canary verbatim. The certificate (KL) and the extraction workloads measure different things,
   and they diverge sharply for this 1.5B target.
2. **The defense comparison is vacuous at this setting.** The headline W5 contrast (B5 content-filter
   brittle ~7× vs LEAKCERT robust ~1×) requires a **non-zero undefended extraction baseline**. With the
   baseline at 0%, every W5/W4 ratio is 0/0 = ∞ and no defense can be differentiated.
3. **Root cause is the decoding setting, not the defense.** The W4/W5 scripts decode at temperature 1.0
   (sampling). Verbatim-memorization extraction should be probed with **greedy / low-temperature
   decoding**. A greedy rerun is the correct next step to obtain a meaningful baseline.

## Next step (in progress)
Greedy-decode rerun: the W4/W5 scripts were updated to honor `model.temperature` from the config, and a
`temperature: 0.0` config (`aau_eval_attacks_greedy.yaml`) reruns the suite to establish whether
verbatim extraction is non-zero under greedy decoding (and only then compare defenses).

## Reproduce
```bash
# on the AAU HPC, in ~/LeakCert
sbatch slurm/eval_attacks.sbatch                       # temperature 1.0 (this run)
LEAKCERT_CONFIG=$PWD/experiments/configs/aau_eval_attacks_greedy.yaml \
  sbatch slurm/eval_attacks.sbatch                     # greedy rerun
```
