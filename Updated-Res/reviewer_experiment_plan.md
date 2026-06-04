# Reviewer-Driven Experiment Plan

This plan translates the simulated reviewer package into concrete next experiments and paper changes. It is scoped for a sanitized public result folder: no venue metadata, no timeline details, no private keys, no local personal paths, and no raw benchmark rows that resemble credentials.

## Executive Diagnosis

The blocking issues are correctness and claim alignment, not just missing scale.

The next revision should prioritize:

1. Enforcing the entropy ceiling `I(K;Y^B) <= H(K)` in every certificate, estimator, and table.
2. Running a dedicated informative-budget evaluation where `B < B* = H(K)/C1`.
3. Decoupling certificate evidence from runtime engineering components such as rate limiting, refusal, and suppression.
4. Correcting the general-prior Fano statement and making prior assumptions explicit.
5. Reframing canary evidence as panel-conditioned auditing unless a real-secret validation experiment is added.

## P0: Correctness Fixes

These must be completed before adding more headline experiments.

| item | action | output |
|---|---|---|
| Entropy cap | Recompute certificate tables with `cert = min(B*C1, H(K))`; report raw `B*C1` only as a diagnostic column | corrected certificate-tightness table |
| Empirical MI sanity | Stop using uncapped MINE as a tightness denominator; report MINE only with an explicit `min(MINE,H(K))` sanity check, or replace with bounded plug-in / attack-derived lower bounds | bounded MI audit table |
| DP table cap | Recompute any DP/RDP table with the same entropy cap and verify the budget/caption uses the actual `B` | corrected DP audit table |
| Fano theorem | State uniform-prior and general-prior forms separately | theorem/proof patch |
| General-prior correction | Use a bound of the form `P_success <= (I + log 2 + log(|K|-1) - H(K))/log(|K|-1)` for non-uniform priors, with assumptions stated | corrected theorem + table notes |

Acceptance gate: every row in every MI/certificate table must satisfy `value <= H(K)` and the machine-readable output must include a boolean `entropy_cap_pass=true`.

## P1: Informative-Regime Certificate Evaluation

Reviewer concern: the empirical win is currently shown mostly at budgets where the certificate is vacuous.

Run a budget sweep around the informative boundary:

| parameter | proposed values |
|---|---|
| canary universe | `|K| = 10^4` if available; otherwise use the largest existing panel and report its `H(K)` |
| budgets | `B = 50, 100, 200, 400, 600, 800, 1000, 2000` |
| required derived value | `B* = H(K)/C1` for each panel |
| methods | B1, B5, LEAKCERT learned-only, cert-only, rate-limit-only, suppression-only, full runtime |
| metrics | extraction, refusal, pass@1/utility, median/p99 latency, capped certificate, raw certificate, `B/B*` |

Required tables:

1. Certificate tightness in the informative regime only (`B/B* < 1`).
2. Transition table showing when the certificate becomes vacuous (`B/B* >= 1`).
3. Runtime-component ablation separating certificate accounting from rate limiting/refusal/suppression.

Safe claim target:

> In the informative regime, the capped certificate remains non-vacuous and tracks bounded leakage diagnostics; beyond the boundary, protection is explicitly runtime/rate-limit driven rather than certificate-driven.

## P2: Replace Fragile Tightness Claims

Reviewer concern: MINE can exceed `H(K)` and is not a reliable ground truth.

Run or compute bounded alternatives:

| estimator / diagnostic | role | cap behavior |
|---|---|---|
| plug-in MI from observed confusion matrix | primary bounded diagnostic when labels are available | naturally bounded by `H(K)` with smoothing |
| Bayes-success / Fano interval | success-to-information consistency check | reports lower/upper consistency, not exact MI |
| bootstrap over panels/seeds | uncertainty for extraction and bounded MI | cap applied per bootstrap sample |
| MINE | optional appendix diagnostic only | must report raw and capped; never used as denominator for tightness |

Required output:

- `certificate_entropy_cap_audit.json`
- `certificate_entropy_cap_audit.md`
- `bounded_tightness_table.md`
- `mine_sanity_check.md`

## P3: Canary-to-Real-Secret Scope

Reviewer concern: the certificate currently certifies the audited canary set, not arbitrary real secrets outside the panel.

Practical response options:

| option | cost | expected value |
|---|---:|---|
| Scope-down only | low | honest but weaker; fastest |
| Synthetic real-secret families | medium | shows panel diversity: API keys, tokens, emails, locations, config secrets |
| Public opt-in benchmark | high | strongest, but needs data governance |

Recommended now:

1. Expand the controlled synthetic secret families already present in the LCCT comparable benchmark.
2. Report per-family extraction and certificate behavior.
3. State that the certificate is panel-conditioned and does not certify secrets absent from `K`.

## P4: Scale and Replication

Reviewer concern: two seeds and small models are not enough for strong claims.

Minimum credible next run:

| dimension | target |
|---|---|
| seeds | at least 5 |
| canary panels | at least 10 if full 20 is too expensive |
| models | current Qwen small + one larger/server checkpoint |
| workloads | W4, W5, W3 utility, informative-budget certificate sweep |
| outputs | per-seed tables, bootstrap CIs, aggregate mean/median, failure analysis |

Server/GPU priority order:

1. Informative-budget certificate sweep.
2. W5 paraphrase replication with 5 seeds.
3. DP/RDP capped audit with real DP checkpoints.
4. Multi-model replication.

## P5: Current Result Interpretation

The current `Updated-Res` package supports the following careful statements:

| result | status | interpretation |
|---|---|---|
| W5 learned-only t=0.95 | strongest current evidence | lower extraction than B5 across two seeds with bootstrap support |
| W3 utility diagnostic | complete but low absolute utility | defense layer is not the main utility bottleneck |
| LCCT comparable full run | complete | current checkpoint does not leak on the controlled comparable benchmark; useful negative-control/readiness evidence |
| certificate non-vacuous | not ready | must be repaired with capped tables and informative-budget runs |
| DP sweep | not ready | needs real DP checkpoints and capped reporting |
| multi-model | not ready | needs second model/checkpoint |

## Immediate Execution Queue

1. Implement an entropy-cap audit script for all certificate/MI tables.
2. Generate corrected certificate and DP audit tables with cap checks.
3. Add an informative-budget config sweep with `B` below and around `B*`.
4. Run a small local pilot of the informative sweep to verify scripts and output schema.
5. Queue the same sweep for server/GPU once available.
6. Update `Updated-Res` with reviewer-facing tables and safe claim wording.

## Stop Conditions

Do not make any headline certificate-tightness claim until:

- all MI/certificate rows pass `<= H(K)`;
- the paper distinguishes raw bound, capped bound, and empirical diagnostic;
- at least one informative-budget table shows non-vacuous certificates;
- rate-limit/refusal/suppression ablations are reported separately;
- theorem statements distinguish uniform and general priors.
