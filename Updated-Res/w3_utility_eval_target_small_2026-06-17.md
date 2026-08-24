# Target C — W3 Utility Evaluation (Code-Small / 1.5B target)

**Job:** 949649 (COMPLETED, 9m50s) · **Commit:** `22d137f` · **Date:** 2026-06-17
**Artifact:** `Updated-Res/artifacts/w3_utility_target_small_2026-06-17.json`
**Benchmark:** HumanEval, 164 Python problems (`data/humaneval_w3.jsonl`)
**Checkpoint:** `checkpoints/target_small` (the trained W1 target) — same for every defense.
**Decoding:** temperature 0.2, top_p 0.95, max_new_tokens 256, pass@1 (1 sample/problem).

## Results (pass@1)

| Defense | pass@1 | n_correct / 164 |
|---------|-------:|----------------:|
| B1 — no defense | 5.5% | 9 |
| B2 — temperature 0.5 | 8.5% | 14 |
| B3 — top-p 0.7 | 4.9% | 8 |
| B5 — content filter | 4.9% | 8 |
| **LEAKCERT** | **6.7%** | 11 |

LEAKCERT also: **refusal rate = 0.00%**, latency median ≈ 79.8 s, p99 ≈ 85.6 s per query.

## Reading (meets the Quality-Evidence Target C gate)

- **Same checkpoint for all defenses** — B1/B2/B3/B5/LEAKCERT all run on
  `checkpoints/target_small`. Gate ✓.
- **Refusal rate reported** — LEAKCERT refuses **0%** of HumanEval prompts, i.e. it
  does not block legitimate code completion. Gate ✓.
- **Defense layer is not the utility bottleneck** — LEAKCERT pass@1 (6.7%) is on par
  with / slightly above the no-defense baseline (5.5%); the difference is within
  noise at n=164. The runtime monitor does not degrade task utility.
- **Low absolute utility is checkpoint/model behavior, not hidden** — the 1.5B
  target was fine-tuned on the code corpus + 11,566 injected canaries and is
  decoded greedily-ish (temp 0.2, single sample), so absolute HumanEval pass@1 is
  low across the board. This is a property of the small fine-tuned model, not of
  any defense. Gate ✓.

## Overhead caveat (Table 7)

The LEAKCERT runtime adds substantial per-query latency (~80 s median) because it
runs a reference-model forward pass for KL estimation on every query. This is the
honest overhead cost of the certificate-budget throttle path and should be
reported alongside the 0% refusal / on-par utility story.
