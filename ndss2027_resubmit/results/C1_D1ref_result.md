# C1 — Non-member control under the D1 (correct) reference: result

**Job:** 1006733, submitted 2026-08-23 07:49, completed 07:54 (4m45s), node a768-l40s-03.
**Command:** `REF=checkpoints/reference_nocanary REF_LABEL=nocanary sbatch slurm/eval_c1_control.sbatch`
**Output:** `ndss2027_resubmit/results/c1_nonmember_control/c1_summary_nocanary.json`

## Setup

- Target: `checkpoints/target_small` (1.5B, fine-tuned on 500k corpus + full ~11,566-canary
  panel, seed 42).
- Reference: `checkpoints/reference_nocanary` (**D1** — same 500k corpus, zero canaries;
  job 1005979, COMPLETED 2026-08-23).
- Member panel: seed 42, `n_per_type=283` (stratified subset of the actually-injected panel;
  verified to be a true deterministic subset — see audit below).
- Non-member panel: seed 999, `n_per_type=283` (structurally identical generator/templates,
  disjoint secret values, never injected into any model).
- Statistic: signed LLR $\hat\kappa_i = \log p_{\text{target}}(k_i\mid c_i) - \log
  p_{\text{D1}}(k_i\mid c_i)$ per canary (`scripts/run_c1_nonmember_control.py`).

## Result

| | member (n=1132) | non-member (n=1132) |
|---|---|---|
| mean | 49.474 | 49.489 |
| median | 10.816 | 11.341 |
| std | 78.775 | 78.149 |
| frac > 0 | 99.1% | 99.5% |

**AUC(member > non-member) = 0.4855** (chance = 0.5) · **mean_gap = −0.0149 nats** · **KS = 0.049**

Per-type AUC: T1_literal 0.488 · T2_paraphrase 0.449 (non-member *higher* than member) ·
T3_semantic 0.517 · T4_vulnerability 0.500. No canary type separates.

**Verdict (script's automatic classification):** *"Member ≈ non-member (AUC=0.49, gap=−0.01) →
under ref=nocanary the exposure is dominated by fine-tuning shift, NOT canary-specific
memorization."*

This is essentially the **same outcome** as the earlier base-ref run (job 1004390: AUC=0.49,
gap=0.001, against the base/untrained model). Using the corrected D1 reference — the entire
purpose of which was to cancel fine-tuning shift and isolate genuine memorization — **did not
change the outcome**: no separation is detectable against either reference.

## Methodology audit (performed before accepting this result)

Checked for a pipeline bug that could produce a false negative before concluding anything:

1. **Panel independence** — `CanaryGenerator(seed=42)` and `CanaryGenerator(seed=999)` each
   own a private `random.Random(seed)` instance; both the secret value *and* the context
   template draw from that seeded stream (`generator.py`). Seeds 42/999 provably generate
   disjoint secret sets. No overlap bug.
2. **Member-panel replay fidelity** — `run_c1_nonmember_control.py::build_panel()` reconstructs
   the panel with the exact same `n_canaries`, `seed=42`, `include_paraphrase`, `n_t3=n_t4=283`
   as `prepare_and_train_target.py::build_panel()` (the code path actually used at injection
   time). `CanaryPanel.stratified_subset()` selects deterministically in first-seen order, so
   the replayed 283-per-type member panel is provably a subset of what was actually injected
   into `target_small`'s training corpus (`canary_injection_manifest.json`). No train/eval
   parameter drift.
3. **Injector cleanliness** — `CorpusInjector.inject_into_dataset()` inserts each canary as an
   independent extra document at a random position; it never modifies existing corpus
   documents. `checkpoints/reference_nocanary`'s corpus is therefore byte-identical to
   `target_small`'s corpus minus exactly the ~11,566 canary lines — no other systematic
   difference between the two training corpora.

**No code defect found.** The null result is accepted as a genuine experimental finding, not a
measurement artifact.

## Interpretation — two (non-exclusive) hypotheses

1. **Single injection is below the detection threshold.** `CorpusInjector` defaults to
   `injection_repeats=1`: each canary is seen at most 3 times total (once per training epoch).
   The memorization literature (e.g., exposure-style measurements) generally finds reliably
   detectable signal only after tens of repetitions; 1 injection in a 500k-document corpus may
   simply be too sparse for this LLR-vs-reference estimator to separate from noise, even if
   some non-zero true memorization exists.
2. **Format-level generalization confound.** All T1 canaries (member and non-member alike)
   share a small, fixed set of context templates and character-class distributions
   (`_AWS_CONTEXTS`, `_JWT_CONTEXTS`, etc., `generator.py`). Training on ~10,000+ member
   canaries following these templates may teach the target model the *general shape* of
   "canary-like" continuations (e.g., "after `AKIA`, predict uniform-random uppercase
   alphanumeric characters") — a legitimate distributional generalization that would inflate
   $\hat\kappa$ for **any** string matching that shape, member or non-member, since both are
   built from the identical generator family. This would mask a smaller, genuine per-instance
   signal underneath a larger, shared format-level effect.

Both hypotheses point the same direction: **this experimental design, at this injection
frequency and this panel structure, does not provide evidence of canary-specific
memorization distinguishable from fine-tuning shift** — using either the base model or the
correct D1 reference.

## Implication for the paper's positioning (§0 of the tracker)

The resubmit strategy committed to keeping the "genuine memorization, separated from
fine-tuning shift" claim, treating D1 as the experiment that would establish it (tracker §0,
line: *"Giữ claim 'memorization thật' ⇒ cần D1"*). **That claim is not supported by the data
we now have.** The honest options, in order of how much rewriting they require:

- **(a) Drop the "genuine memorization exists" claim entirely.** Reframe the paper's
  contribution around what *is* supported: an honest, falsifiable auditing methodology and
  certificate machinery (Lemma 0, Theorems 5′/7′/10′/13′/17′, §`A_theory_corrections_draft.md`)
  demonstrated on a panel where — after correcting the reference-model confound the original
  submission missed — **no memorization signal was detected**, which is itself a legitimate,
  honestly-reported negative result and consistent with the paper's other retraction (SPRT
  claim, A5) and honest-audit framing (A9–A13).
- **(b) Report both C1 results as a limitations/negative-result subsection**, explicitly
  distinguishing "the tool can detect memorization when present" (not yet shown either way,
  since no positive-control experiment with higher repetition was run — see A2/appendix note)
  from "we did not detect it in this specific single-injection, 3-epoch configuration."
  This is the most defensible framing given what has actually been measured.
- **(c) Do not claim anything about memorization prevalence one way or the other** and pivot
  the paper's headline entirely to the certificate/audit-methodology contribution plus the
  SPRT-retraction finding (already the strongest result per tracker's "Điểm mạnh" section),
  treating the memorization measurement as inconclusive rather than negative.

**Recommendation:** (b). It is the most scientifically honest given the audit above found no
pipeline defect, it does not overclaim a negative ("memorization does not exist") from a single
configuration, and it is consistent with the honest-audit repositioning already underway in
`A_theory_corrections_draft.md` (A9–A13, A11).

## Cross-references
- `results/C1_base_ref_result.md` — the earlier base-ref run (same null pattern).
- `results/A_theory_corrections_draft.md` §0/A11 — needs updating to reflect this result before
  finalizing the "first non-vacuous certificate" retraction language.
- `ndss2027_resubmit_progress.md` §0 and NHÓM C row C1 — updated 2026-08-23 with a pointer to
  this file.
