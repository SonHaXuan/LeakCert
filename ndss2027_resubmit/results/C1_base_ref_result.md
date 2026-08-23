# C1 — Non-member control under the base-model reference: result

**Status:** recovered/rewritten 2026-08-23. This file is referenced by
`C1_D1ref_result.md` and `A_theory_corrections_draft.md` (§A3) but was never committed to git —
the commit that produced it (`02d3199`, 2026-08-18) wrote it to a then-gitignored `results/`
path, so only the commit message survives. That message is a real, git-verifiable primary
source and is quoted directly below; no numbers here are invented.

**Job:** 1004390, ~4 minutes, 2026-08-18.
**Source:** commit `02d31994add86a3412f808e91420fbf0a35d58bf` ("C1 base-ref result
(fine-tuning-shift smoking gun) + 7B attack eval setup").

## Setup

- Target: `checkpoints/target_small` (1.5B, fine-tuned on 500k corpus + full canary panel, seed
  42) — same target used later in `C1_D1ref_result.md`.
- Reference: **base model** `models/qwen2.5-coder-1.5b` (untrained/pre-fine-tuning), i.e. the
  reference available *before* D1 (the matched-corpus, no-canary reference) was trained. This
  run predates D1 (job 1005979 completed 2026-08-23) by five days — it is the original,
  un-corrected reference the paper started with.
- Member vs. non-member panel construction, statistic (signed LLR), and script
  (`scripts/run_c1_nonmember_control.py`) are the same methodology later reused for the D1-ref
  run — see `C1_D1ref_result.md` §Setup for the full description (panel seeds 42/999,
  `n_per_type=283`, `n=1132` per side).

## Result (quoted from commit `02d3199`)

> "member vs non-member LLR indistinguishable under the base reference (**AUC 0.49, gap
> 0.001**). Even the flagged 156-nat T3 exposure is present equally in never-injected canaries
> (**155.6 vs 156.5**) → the old exposure measures fine-tuning shift, not memorization."

| | value |
|---|---:|
| AUC (member > non-member) | **0.49** (chance = 0.5) |
| mean_gap | **0.001** nats |
| T3_semantic exposure, member | ~156.5 nats |
| T3_semantic exposure, non-member | ~155.6 nats |

The T3 comparison is the sharpest part of this result: the paper's headline "T3 exposure ≈ 156
nats" figure — cited elsewhere as evidence of strong semantic memorization — is **present at
essentially the same magnitude in canaries that were never injected into the model**. Under the
base reference, that ~156-nat number is measuring the gap between the *fine-tuned* model and the
*untrained* base model on T3-shaped text in general, not anything specific to the injected
secrets.

## Interpretation

This is the run that originally motivated D1: the reasoning at the time (see tracker §0, "Chốt
mức resubmit (2026-08-17): CHUẨN — train đúng 1 model D1") was that the base-model reference
confounds two effects — (a) generic fine-tuning shift (the model changes for *any* fine-tuning,
canaries or not) and (b) canary-specific memorization — and that training D1 (same corpus, zero
canaries) would cancel (a) and isolate (b).

**That prediction did not hold.** `C1_D1ref_result.md` shows the D1-corrected run (job 1006733,
five days later) reproduces the same null result (AUC=0.4855, gap=-0.0149) using the reference
that was specifically built to remove the fine-tuning-shift confound. The two runs together —
not either one alone — are the actual evidence for the tracker's current conclusion (§0,
2026-08-23 entry): the "genuine memorization, separable from fine-tuning shift" claim is not
supported by data under **either** reference model.

## What this file does NOT contain

Unlike `C1_D1ref_result.md` (which has the full per-type AUC breakdown and a from-scratch
methodology audit against `generator.py`/`injector.py`), this file only has the top-line
numbers preserved in the commit message. The original `results/C1_base_ref_result.md` write-up
and its synced `c1_summary_base.json` are not recoverable — if a full per-type breakdown or the
raw per-canary LLR values for job 1004390 are needed, the source data no longer exists and the
run would need to be repeated (base model + `checkpoints/target_small` are both still on the
HPC, so this is re-runnable via `REF=models/qwen2.5-coder-1.5b REF_LABEL=base sbatch
slurm/eval_c1_control.sbatch` if exact reproduction is required).

## Cross-references

- `results/C1_D1ref_result.md` — the corrected-reference rerun; read together, these two files
  are the full C1 evidence base.
- `results/A_theory_corrections_draft.md` §A3, §A11 — cites this result as part of the
  fine-tuning-shift discussion and the headline-claim retraction.
- `ndss2027_resubmit_progress.md` §0 and NHÓM C row C1.
