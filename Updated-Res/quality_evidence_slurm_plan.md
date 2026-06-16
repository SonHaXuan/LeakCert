# Quality-Evidence Plan — Slurm mapping (target_small + target_mid)

Maps Son's `server_deploy/QUALITY_EVIDENCE_RUNBOOK.md` (commit `de4a792`,
Targets A–E + acceptance gates) onto our AAU Slurm workflow. His pipeline assumes
a single-host `LEAKCERT_RUN_ROOT` server; we keep the *targets and gates* and run
them as Slurm jobs against `checkpoints/target_small` (done) and
`checkpoints/target_mid` (training, job 948769).

Status legend: ✅ done · 🟡 partial/needs rerun · ⬜ not started · ⏳ in progress

---

## Current standing vs the five targets

| Target | What it needs | Standing |
|--------|---------------|----------|
| **A** Full W4/W5 | 283/type, n_eval=1132, budget 10000, per-mode+per-type, audit rows | 🟡 ran at reduced 100-canary scale; **0% verbatim** both baseline+method |
| **B** Informative cert | kl_estimates, capped tables, B* sweep, cap audit; one `0<cert<H(K)` | ✅ T4 B=1 → 2.645 nats < H 5.645 (P≤57.4%). Cleanup: `is_vacuous` float artifact |
| **C** Utility W3 | same checkpoint+defenses as extraction; refusal rate | 🟡 measured earlier, **not on real target_small** |
| **D** Stress + ablation | component ablation (4 monitor parts separately) + attack stress | ⬜ A-adaptive only; no component ablation |
| **E** DP + multi-model | real checkpoints; full W3/W4/W5/cert per ckpt | ⏳ 7B training (948769); DP deferred |

---

## Job 1 — Target A: Full W4/W5 replication (target_small)

**New config** `experiments/configs/aau_eval_attacks_full.yaml`: clone of
`aau_eval_attacks.yaml` with `n_eval_per_type: 283`, `n_eval: 1132`; defenses
`[B1, B5, LEAKCERT]`; budget 10000; keep both sampled (temp from model) and a
greedy pass (`temperature: 0.0`) for the verbatim contrast.

**Slurm**: reuse `slurm/eval_attacks.sbatch` (runs `run_w5_paraphrase.py` +
`run_w4_code_secret.py`), launch with
`LEAKCERT_CONFIG=.../aau_eval_attacks_full.yaml`. Single a10/L40S. Bump
`--time` to `24:00:00` (≈11× the 100-canary run).

**Gate checks**: same checkpoint+panel ✓ (config pins `target_small`, seed 42);
emit **per-mode AND per-type** rates (scripts already do); dump audit rows
(no private strings). Honesty note: our real result is **0% both arms**, so the
"W5 CI excludes zero" gate cannot be forced — we report per-mode/per-type 0%
explicitly and frame "likelihood memorization ≠ verbatim extractability" rather
than claim a fake improvement. This is the faithful outcome to put in the report.

## Job 2 — Target B: cert-sweep cleanup + re-emit (CPU, fast)

**Code fix**: in `experiments/run_certificate_sweep.py` (or the certificate
module), fix the `is_vacuous` float artifact so capped rows are flagged vacuous
(`is_vacuous = capped_cert >= H(K) - eps`). Re-tag, don't recompute KL.

**Slurm**: reuse `slurm/eval_lrt_sweep.sbatch` (CPU-only, reuses
`kl_estimates.json`). ~20 min. Re-emit `certificate_sweep.json` + entropy-cap
audit with the corrected flag and a clean diagnostic-vs-capped split.

**Gate checks**: every value ≤ H(K) ✓; one real `0<cert<H(K)` (T4 B≤2) ✓;
zero-KL labeled diagnostic ✓.

## Job 3 — Target C: W3 utility on the real checkpoint (target_small)

**Dependency**: `run_w3_real_completion.py` needs a utility eval set
(`corpus.utility_eval_path` is empty in `aau_paper_scale.yaml`). Resolve a real
code-completion benchmark JSONL on the server (or reuse the earlier W3 set) and
set the path; otherwise this is a **stop condition** (no synthetic fallback).

**New Slurm** `slurm/eval_w3_utility.sbatch` (clone of `eval_certificate.sbatch`
shape): runs `run_w3_real_completion.py --config aau_paper_scale.yaml` with
defenses B1/B5/LEAKCERT all on `checkpoints/target_small`. Single GPU, ~2–4h.

**Gate checks**: B1/B5/method same checkpoint ✓; report **refusal rate**; frame
low absolute pass@1 as model behavior, not hidden.

## Job 4 — Target D: component ablation + attack stress (target_small)

**4a Component ablation** — report the 4 runtime-monitor parts separately
(budget throttle, rate limiter, φ_u refusal, regex/hash suppression). Son's
runner exposes `LEAKCERT_RUN_COMPONENT_ABLATION`; new
`slurm/eval_ablation.sbatch` runs it on a large panel (≥283/type). ~3–6h.

**4b Attack stress** — A-adaptive at budgets `[100,1000,10000]` × `[B1,B5,LEAKCERT]`
on `aau_eval_attacks.yaml`. Expensive (~6.5h/pair). Run as a **Slurm array**
(one task per budget×defense, isolated session/API key per task), `--time 12:00:00`
each. Do this only **after** Job 1 (core full) passes, per the runbook ordering.

**Gate checks**: isolated keys/sessions per task ✓; panel large enough for the
ablation claim; refusal / rate-limit / accounting / suppression reported
separately ✓.

## Job 5 — Target E: 7B multi-model (target_mid), after 948769 finishes

Once `checkpoints/target_mid` exists, rerun the suite against it by pointing the
same jobs at the mid checkpoint:
- certificate: `eval_certificate.sbatch` with a `target_mid` config (`compute_certificate.py`);
- W4/W5: Job 1 config variant on `target_mid`;
- W3: Job 3 on `target_mid`.

DP sweep stays **deferred** (full-500k DP-SGD single-GPU >48h; 0% verbatim makes
extra DP checkpoints low-value; Table 8 DP-vs-cert is already analytic). Only
claim multi-model robustness if `target_mid` reloads and all of W3/W4/W5/cert run.

---

## Cross-cutting — evidence packaging (applies to every job)

Each run dir must carry: copied config · command logs · `git rev-parse HEAD` ·
input-validation output · result JSON/JSONL/MD · entropy-cap audit (cert jobs) ·
`manifest.json` with file sizes + SHA-256. Add a small post-step (adopt Son's
`collect_results.sh` / `run_quality_evidence_pipeline.sh collect`) at the tail of
each sbatch, or a shared `slurm/_collect.sh`. Refuse to publish from a dirty git
tree (stop condition).

## Suggested order (respects runbook gating)

1. **Job 2** (cert cleanup, CPU, ~20 min) — closes B cleanly, no GPU contention.
2. **Job 1** (full W4/W5) — the core full run; A.
3. **Job 3** (W3 utility) — once the utility JSONL is resolved; C.
4. **Job 4a/4b** (ablation + stress) — only after Job 1 passes; D.
5. **Job 5** (7B suite) — when 948769 completes; E.
