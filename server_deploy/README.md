# LeakCert Server Deployment

This folder contains the minimal server-side workflow for reproducing LeakCert
smoke and small/medium evaluation runs on a borrowed server.

The scripts assume you have cloned the repository on the server:

```bash
git clone https://github.com/SonHaXuan/LeakCert.git
cd LeakCert
```

Do not put API keys, SSH keys, checkpoints, or large datasets in git. Put them
in a private run root such as `/data/LeakCert_runs` or `$HOME/LeakCert_runs`.

## 0. Preflight

Run this first. It records OS, CPU, RAM, disk, Python, GPU, and CUDA status.

```bash
bash server_deploy/run_preflight.sh
```

The preflight log is written to:

```text
_run_logs/server_preflight_<timestamp>.log
```

## 1. Setup

Use Python 3.11 or 3.12. PyTorch may not support Python 3.14 yet, so the setup
script intentionally refuses Python 3.14 unless you override it with a working
interpreter.

```bash
export LEAKCERT_RUN_ROOT=/data/LeakCert_runs
export LEAKCERT_PYTHON=python3.12   # or python3.11
bash server_deploy/setup_server.sh
```

If the server has no `/data`, use:

```bash
export LEAKCERT_RUN_ROOT=$HOME/LeakCert_runs
```

The setup script creates:

```text
.venv/
$LEAKCERT_RUN_ROOT/hf_cache/
$LEAKCERT_RUN_ROOT/results/
$LEAKCERT_RUN_ROOT/logs/
```

## 2. Smoke Test

Run a tiny CPU-safe DP smoke before any expensive training:

```bash
bash server_deploy/run_smoke.sh
```

Expected output:

- tiny corpus generated
- DP accounting JSON written
- checkpoint reload succeeds
- manifest generated

## 3. Small GPU Evaluation

Only run this if preflight shows an NVIDIA GPU and enough disk.

```bash
export LEAKCERT_MODEL=Salesforce/codegen-350M-mono
export LEAKCERT_ROWS=64
export LEAKCERT_EPSILONS=2,8,16
bash server_deploy/run_small_gpu_eval.sh
```

This runs a modest DP sweep using `scripts/run_local_dp_smoke.py`, then runs
Phase A and Phase B smoke evaluation against the epsilon-8 checkpoint if it is
available.

Results are written under:

```text
$LEAKCERT_RUN_ROOT/results/server_small_<timestamp>/
```

## 4. Collect Results

Create a compact archive containing logs, configs, metrics, and manifests. It
excludes full model weights by default.

```bash
bash server_deploy/collect_results.sh "$LEAKCERT_RUN_ROOT/results/server_small_<timestamp>"
```

The archive path will be printed. Copy that archive back to your local machine:

```bash
scp user@server:/path/to/leakcert_results_<timestamp>.tgz .
```

## Evidence Policy

For SP-quality evidence, every run should keep:

- git commit hash
- command line
- config copy
- stdout/stderr log
- metadata JSON
- metrics JSON/CSV
- manifest with file sizes and hashes when possible

Do not claim paper-grade DP/multi-model results from smoke runs. Smoke runs are
only for verifying that the environment and pipeline are healthy.
