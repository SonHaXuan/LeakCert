# LeakCert

**Extraction-Resistant Code Completion with Information Leakage Certificates**

LeakCert studies how language models memorize sensitive data ("canaries") planted
in fine-tuning data, formally bounds how much of that information an attacker can
extract using mutual-information theory, and defends against extraction attacks
with a runtime monitor. This repository contains the reference implementation
used to produce the results in the accompanying paper.

> **Built with AI assistance.** This codebase was developed with substantial
> help from AI coding agents (Claude Code). Code released alongside our paper
> submission; author and institution details are withheld pending peer review.

## Overview

The pipeline flows: **canary injection → fine-tuning → KL estimation →
certificate → attacks → runtime monitor → evaluation**.

- **Canaries** (`leakcert/canary/`) — four secret types (literal, paraphrase,
  semantic, vulnerability) injected into the fine-tuning corpus exactly once.
- **Fine-tuning** (`leakcert/model/`) — standard SGD or DP-SGD (via Opacus)
  training of a HuggingFace causal LM.
- **Certificate** (`leakcert/certificate/`) — five theorems bounding
  extractable information (in nats — natural log units throughout) from
  per-canary KL-divergence estimates (likelihood-ratio, self-ratio, or
  MIA-classifier methods).
- **Runtime monitor** (`leakcert/runtime/`) — a four-stage online defense:
  certificate-budget throttle → per-key rate limiter → uncertainty-refusal
  classifier → regex/hash target-string suppression.
- **Attacks** (`leakcert/attacks/`) — five extraction strategies, from static
  templates to an adaptive UCB-bandit attacker and a gradient-free
  Carlini-style search.
- **Defenses** (`leakcert/defenses/`) — six baselines (no defense,
  temperature, top-p, rate limiting, content filtering) plus the full
  LeakCert runtime monitor.
- **Evaluation** (`leakcert/evaluation/`) — five workloads (W1–W5) and eight
  standardized scenarios (E1–E8), orchestrated by `ExperimentConfig` in
  `runner.py`.

### Extending the framework

- **New attack** — subclass `Attacker`, implement `attack_canary()`.
- **New defense** — subclass `DefenseWrapper`, implement `complete()`.
- **New workload** — subclass `Workload`, implement `samples()`.
- **New scenario** — add a dataclass to `e_scenarios.py`, register it in
  `runner.py`.

## Installation

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
```

## Quickstart

A CPU-only smoke test validates the core pipeline end-to-end in about 15
minutes:

```bash
python scripts/run_phase_a_smoke.py
```

Run the test suite and static checks:

```bash
pytest tests/ -v --cov=leakcert
black leakcert/ tests/ scripts/
ruff check leakcert/ tests/ scripts/
mypy leakcert/
```

## Reproducing paper results

Full-scale experiments require GPU hardware and are driven by config files in
`experiments/configs/`. Two deployment paths are provided:

- `server_deploy/` — preflight → setup → data bundle → run
  (`smoke`/`small`/`full`) workflow for a single GPU host.
- `slurm/` — job scripts for a Slurm-managed HPC cluster (see
  `slurm/README.md`).

All experiments use 5 seeds (`42, 137, 271, 314, 999`) with 500K-sample
bootstrap confidence intervals. `Updated-Res/` contains the sanitized result
tables, artifacts, and paper-ready summaries produced by this pipeline; see
`Updated-Res/README.md` for the headline findings and their current
evidentiary strength.

## Repository layout

```
leakcert/          Core library (canary, model, certificate, runtime, attacks, defenses, evaluation)
experiments/        Experiment entry points (W1-W5 workloads) and configs
scripts/            Data-prep, analysis, and result-packaging utilities
slurm/              Slurm job scripts for HPC training/evaluation
server_deploy/       Single-host GPU deployment workflow
tests/              Unit tests
Updated-Res/         Sanitized results, tables, and supporting artifacts
```

## License

MIT — see [LICENSE](LICENSE).
