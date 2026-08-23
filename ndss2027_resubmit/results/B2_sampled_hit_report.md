# B2 — Reporting the one sampled-decoding hit directly

**Status:** recovered/rewritten 2026-08-23, with an explicit data-availability caveat (see §2).
The tracker row this file backs reads: *"1/142632, T4 pattern, ambiguous/false-pos, chỉ B1"* — this
document reconstructs the analysis that claim implies, but **the raw generation/audit log for that
specific 142,632-query aggregate no longer exists anywhere in this repository or its git
history** (confirmed: `git log --all` on every plausible path returns nothing, and no local or
gitignored `results/`/`_run_results/` directory contains it). Rather than invent the missing
content, this file separates what is independently verifiable from what is not.

## 1. The ask

Several places in the extraction-rate evaluation report exactly **one** non-zero hit out of a very
large number of sampled-decoding queries, then round it to 0.00% and move on. The reviewer-facing
ask (B2) is: don't bury it — report the hit directly (what it was, which defense, which canary
type) and characterize it explicitly as true/false/ambiguous, rather than letting a rounded "0.00%"
imply a clean sweep.

## 2. What is independently verifiable in this repository

`Updated-Res/attack_eval_target_small_2026-06-10.md` (job 944415, W5 paraphrase workload, target
`checkpoints/target_small`, 100-canary panel) documents exactly this pattern at a smaller scale:

> "The single W5 hit (1/12,600 audit rows total) was a `natural_language` paraphrase under B1 —
> statistically noise." (line 25)

and the accompanying table (line 21) shows the same event at the W5-table level: **B1 no_defense:
0.03% (1/3500)**, i.e. the "1" in that 1/3500 is the same hit as the "1/12,600" figure quoted in
the prose (12,600 = the full audit-row count across all paraphrase modes/canaries for that run,
vs. 3,500 = the W5 Table-6 subset of it). This is a **verified, primary-source** data point:

| Field | Value |
|---|---|
| Run | job 944415, 2026-06-10, `aau_eval_attacks.yaml`, target_small (1.5B) |
| Denominator | 1/3500 (W5 Table 6 rate) = 1/12,600 (full audit-row count) |
| Defense | B1 (no_defense) only — not reproduced under B5 or LEAKCERT |
| Paraphrase mode | `natural_language` |
| Classification (as documented) | statistical noise (i.e., a **false-positive-leaning / ambiguous** match, not a confirmed verbatim leak) |

Recomputed exact 95% CP CI for this event (`compute_cp_ci.awk -v x=1 -v n=3500`):
**0.029% [0.0007%, 0.159%]** — consistent with "0.00%" only under rounding; correctly reported as a
non-zero point estimate with a CI that still comfortably excludes any claim of systematic leakage.

## 3. What is NOT verifiable — the "1/142632" figure specifically

The tracker's B2 row cites a **different, larger** denominator (142,632) than the one documented
above (3,500 / 12,600). 142,632 is roughly 11x the 12,600-row audit from the June run, consistent
with a later, larger paper-scale sweep (more seeds and/or the full 283/canary-type panel rather
than the 25/type reduced panel) — but no file, log, or git commit in this repository records:

- which run/job produced it,
- which canary or canary type the hit belongs to (the tracker says "T4 pattern," which is *plausible*
  given T4 = vulnerability-pattern canaries are the most likely to trigger incidental string
  matches, but this is inference from the tracker's one-line note, not a checked fact),
  the tracker also states it is "ambiguous/false-pos," consistent with §2's pattern.
- the exact generated text or the audit rule that flagged it,
- which defense condition (the tracker says "chỉ B1," i.e. only under no-defense — consistent with
  §2's pattern, but again not independently checked here).

**Do not present a fabricated transcript or canary ID for this event.** If the paper's current
draft already quotes specific details (secret content, canary ID, exact generated string) for the
142,632-denominator hit, those details predate this recovery and this document cannot confirm or
deny them — they should be re-verified against whatever machine actually ran that sweep, or the
sweep should be re-run to regenerate a checkable artifact.

Recomputed exact 95% CP CI for the aggregate figure as-cited (`compute_cp_ci.awk -v x=1
-v n=142632`, taking the numbers at face value): **0.0007% [0.000018%, 0.0039%]**.

## 4. Recommendation

1. Report the §2 event directly in the paper as the primary worked example — it is the one hit this
   repository can actually verify end to end (run ID, config, denominator, classification):
   *"of 12,600 sampled-decoding audit rows (100-canary W5 panel, 5 paraphrase modes, undefended
   target), exactly one row matched — a `natural_language`-paraphrase prompt whose completion
   triggered the string-match rule as a false positive / ambiguous match, not a confirmed verbatim
   secret. 95% CP CI: [0.0007%, 0.159%]."* This directly satisfies the B2 ask (report the hit, don't
   round it away) with a fully traceable source.
2. For the larger 142,632-denominator aggregate: either (a) re-run the sampled-decoding audit at
   paper scale and regenerate the artifact so the specific hit can be verified and described
   accurately, or (b) drop the 142,632 figure from the paper if it cannot be re-verified, and rely
   on the §2 result (which makes the same qualitative point — one incidental non-leak hit out of a
   large sampled-decoding sweep — with a source that survives an audit).
3. Whichever path is chosen, do not report a bare "0.00%" for either sweep without a footnote
   pointing to this non-zero hit and its classification — that is the actual B2 finding.

## 5. Reproduce

```bash
cd ndss2027_resubmit/results
awk -f compute_cp_ci.awk -v x=1 -v n=3500     # W5 Table-6 denominator, verified event
awk -f compute_cp_ci.awk -v x=1 -v n=12600    # full audit-row denominator, verified event
awk -f compute_cp_ci.awk -v x=1 -v n=142632   # paper-scale figure as cited, unverified source
```
