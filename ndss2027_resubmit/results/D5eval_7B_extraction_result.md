# D5-eval — 7B attack suite (W4/W5) vs. 1.5B: does the larger model verbatim-leak?

**Status:** recovered/rewritten 2026-08-23. The tracker row and commit `56291b3` ("7B attack eval
result: 7B verbatim-leaks 10-16% where 1.5B is 0%") are real, committed, primary-source records —
the headline numbers below are quoted from that commit and are not fabricated. However, the raw
per-canary/per-mode JSON artifacts it references (`results/D5eval_7B_extraction_result.md` in its
pre-loss form, plus the `attacks_7b/` directory) were never committed to git (both live under
gitignored `results/`/`_run_results/` paths) and are not present on this machine. **This document
reconstructs the headline result and its documented caveats from the commit record; it does not
reconstruct the per-canary breakdown, since that never made it into version control.**

## 1. Question

The 1.5B target (`checkpoints/target_small`) showed **0% verbatim extraction** across every
attack surface tested (W4 static templates, W4 A-adaptive UCB bandit, all 5 W5 paraphrase modes —
see `Updated-Res/attack_eval_target_small_2026-06-10.md` and `aau_hpc_eval_results_2026-08-14.md`
§7/§7a), despite the certificate showing strong latent memorization (mean KL ≈ 20 nats). This
raises an obvious question the paper needs to close off: **is 0% verbatim extraction a property of
this framework's attacks being too weak, or a property of the 1.5B model?** D5-eval answers this
by running the identical attack suite against a much more over-memorized 7B checkpoint.

## 2. Setup (from `experiments/configs/aau_eval_attacks_mid.yaml`, still present in this repo)

| Field | Value |
|---|---|
| Target | `checkpoints/target_mid_sub2/checkpoint-20614` (Qwen2.5-Coder-7B, fine-tuned) |
| Reference | `models/qwen2.5-coder-7b` (base) |
| Canary panel | seed 42, 25/type × 4 = 100 canaries, deterministic subset of the 11,566 injected (same panel-construction method as the 1.5B run, see `leakcert/canary/generator.py` audit in `A_theory_corrections_draft.md`) |
| Decoding | temperature 1.0, max_new_tokens 128 |
| Defenses run | B1 (none), B5 (content filter), LEAKCERT |
| Adaptive budget | B=100 only (B=1000/10000 explicitly deferred as intractable on one L40S, same reasoning as the 1.5B run) |
| Job | 1004391 (`eval_attacks_mid.sbatch`), run opportunistically while D1 was training |
| **Known caveat baked into the setup** | the 7B was fine-tuned as a memorization *stress test*, not on a corpus matched in scale to the 1.5B's 500k-doc corpus — see A14 in `A_theory_corrections_draft.md` for how this caveat propagates into the paper's framing |

## 3. Headline result (quoted from commit `56291b3`, 2026-08-19)

> "Headline: identical attack suite on the over-memorized 7B (loss 0.044) recovers secrets in
> 10.3% of static W4 probes and 16% under A-adaptive (vs 1.5B 0%). Confirms the 1.5B 0% is a model
> property, not weak attacks."

| Metric | 1.5B (target_small) | 7B (target_mid_sub2) |
|---|---:|---:|
| W4 static (Path A) verbatim extraction | **0.00%** (0/700) | **~10.3%** |
| W4 A-adaptive, B=100 (Path B) | **0.00%** (0/100) | **~16%** |
| W5 paraphrase (all modes) | **0.00%** (0/3500) | **~8%** |
| Training loss at checkpoint | — (target_small not reported at this granularity) | **0.044** (over-memorized) |

Tracker also records two open findings that were flagged for follow-up, not yet resolved:

1. **Defenses did not reduce leakage on the 7B** — B5 (content filter) and LEAKCERT both failed to
   bring the 7B's extraction rate down from the undefended baseline. This is unexpected (on the
   1.5B, LEAKCERT measurably raised T1 query cost — see `aau_hpc_eval_results_2026-08-14.md` §8)
   and is marked in the tracker as "cần điều tra" (needs investigation) — **not yet investigated**,
   since the underlying per-defense breakdown JSON is the artifact that was lost.
2. **LRT stage may have timed out** — the tracker notes "LRT có thể timeout (đã lưu W4/W5)," i.e.
   the W4/W5 results were saved (incremental-flush fix from `aau_hpc_eval_results_2026-08-14.md`
   §10 was already in place by this point) but the LRT/MIA stage for the 7B may not have completed.
   No LRT number for the 7B is quoted anywhere in the tracker or commit history — treat 7B LRT as
   **not run / not confirmed**, not as "0% like the 1.5B."

## 4. Interpretation

- **The 1.5B's 0% verbatim extraction is not an artifact of a weak attack suite.** The identical
  W4/W5 pipeline, on a checkpoint trained to memorize harder (loss 0.044 vs. whatever the 1.5B's
  final loss was), recovers secrets at double-digit rates. This is the load-bearing evidence for
  keeping the certificate-vs-extraction-rate distinction as a paper contribution rather than a
  confound: the certificate's high-KL signal on the 1.5B was not simply "wrong" or "too
  sensitive" — a model that memorizes harder *does* leak under the same attacks.
- **The corpus-mismatch caveat (A14) limits how far this can be pushed as a clean scaling claim.**
  The 7B was deliberately over-trained as a stress test on a different corpus scale than the 1.5B's
  matched-scale target. This result supports "verbatim extractability is a function of degree of
  memorization" (consistent with the loss=0.044 framing) but does **not** support a clean "7B
  parameters leak more than 1.5B parameters at matched training" claim — that would require D5 (a
  7B trained on a corpus matched to the 1.5B's, currently unrun, tracker status ⬜) rather than
  D5-eval's stress-test checkpoint.
- **The defense-doesn't-help finding is a genuine open thread, not a resolved negative result.**
  Unlike C1 (audited, no bug found, documented as negative-result), this finding was never
  followed up — the artifact needed to investigate it (per-canary/per-defense breakdown) is the
  one lost in the `results/`-gitignore incident. If this claim is going to appear in the paper, it
  needs re-running with the now-fixed periodic-checkpoint/incremental-save infrastructure so the
  breakdown survives this time.

## 5. What would be needed to close remaining gaps

1. Re-run `eval_attacks_mid.sbatch` against `checkpoints/target_mid_sub2/checkpoint-20614` (the
   checkpoint itself should still exist if not pruned) to regenerate the per-canary/per-defense
   JSON, so the "defenses don't help on 7B" claim can actually be investigated rather than just
   flagged.
2. Explicitly re-run or confirm the LRT/MIA stage for the 7B (currently unconfirmed either way).
3. If a clean scaling claim (not just a stress-test existence proof) is wanted for the paper, that
   is D5 (train 7B on a corpus matched to the 1.5B), which remains unrun (⬜ in the tracker) and is
   a materially larger GPU-time ask than D5-eval.

## 6. Source

- Commit `56291b3c81dc75dbc1c2f1f532fe6ac99b1c52fa` (2026-08-19, "7B attack eval result: 7B
  verbatim-leaks 10-16% where 1.5B is 0%") — primary source for all headline numbers in §3.
- `ndss2027_resubmit/ndss2027_resubmit_progress.md` row D5-eval — same numbers, tracker framing.
- `experiments/configs/aau_eval_attacks_mid.yaml`, `slurm/eval_attacks_mid.sbatch` — setup detail,
  still present in this repo and usable to re-run per §5.
