# LeakCert Server Deployment

This folder is the server-side deployment kit for evaluation runs that need
more hardware than a local workstation. It is designed for a fresh server where
the repository is cloned from GitHub but private data/checkpoints are not
present.

The workflow is intentionally gated:

1. clone code;
2. setup environment;
3. copy only required private artifacts from the local machine;
4. verify data/checkpoints;
5. run smoke;
6. run small/full server evaluations only after smoke passes;
7. collect logs/results without copying full model weights unless requested.

Do not commit API keys, SSH keys, raw private data, checkpoints, or paper files.

## 0. Clone On Server

```bash
git clone <this-repo-url>
cd LeakCert
git rev-parse HEAD
```

Use a private run root with enough disk:

```bash
export LEAKCERT_RUN_ROOT=/data/LeakCert_runs
# fallback if /data does not exist:
# export LEAKCERT_RUN_ROOT=$HOME/LeakCert_runs
```

## 1. Server Preflight

```bash
bash server_deploy/run_preflight.sh
```

This records OS, CPU, RAM, disk, Python, GPU/CUDA, and git commit in
`_run_logs/server_preflight_<timestamp>.log`.

## 2. Setup Environment

Use Python 3.11 or 3.12. Current PyTorch wheels may not support newer Python
versions reliably.

```bash
export LEAKCERT_PYTHON=python3.12
bash server_deploy/setup_server.sh
```

The setup creates `.venv/` and cache/result folders under `$LEAKCERT_RUN_ROOT`.

## 3. Prepare Data Bundle On Local Mac

On the local machine that already has the data/checkpoints, copy the example
manifest and edit only paths that exist locally:

```bash
cp server_deploy/required_data_manifest.example.json _run_results/server_data_manifest.json
$EDITOR _run_results/server_data_manifest.json
```

Then create a private bundle:

```bash
.venv/bin/python server_deploy/make_data_bundle.py \
  --manifest _run_results/server_data_manifest.json \
  --output-dir _run_results/server_payloads
```

The script prints a `.tgz` path. Copy it to the server:

```bash
scp _run_results/server_payloads/leakcert_server_payload_*.tgz user@server:/tmp/
```

The bundle should include only the minimum needed artifacts:

- real training corpus JSONL for W1/DP/multi-model;
- real LCCT/comparable JSONL if running W2;
- existing target checkpoint if you want to skip W1 training;
- optional second-model checkpoint;
- optional per-epsilon DP checkpoints and `dp_accounting.json`;
- refusal calibrator if the config uses one.

## 4. Install Data Bundle On Server

```bash
.venv/bin/python server_deploy/install_data_bundle.py \
  --bundle /tmp/leakcert_server_payload_<timestamp>.tgz \
  --run-root "$LEAKCERT_RUN_ROOT"
```

This extracts files into `$LEAKCERT_RUN_ROOT`, verifies SHA-256 hashes, and
writes:

```text
$LEAKCERT_RUN_ROOT/configs/server_real_inputs.yaml
$LEAKCERT_RUN_ROOT/data_bundle_manifest.installed.json
```

## 5. Validate Inputs

```bash
.venv/bin/python scripts/validate_real_inputs.py \
  --config "$LEAKCERT_RUN_ROOT/configs/server_real_inputs.yaml" \
  --output-dir "$LEAKCERT_RUN_ROOT/results/input_validation_$(date +%Y%m%d_%H%M%S)"
```

If this returns code `75`, it found blockers. Do not run full evaluations until
the blockers are fixed.

## 6. Smoke Before Full

Always run smoke first:

```bash
export LEAKCERT_CONFIG="$LEAKCERT_RUN_ROOT/configs/server_real_inputs.yaml"
bash server_deploy/run_server_evaluations.sh smoke
```

Smoke mode runs:

- resource snapshot;
- real-input validation;
- server preflight;
- tiny DP smoke;
- W2 real-input smoke if LCCT data and checkpoint exist;
- W4/W5/certificate smoke if checkpoint exists.

If smoke passes, run a small server pass:

```bash
bash server_deploy/run_server_evaluations.sh small
```

Run full only after small passes and the server budget is acceptable:

```bash
bash server_deploy/run_server_evaluations.sh full
```

## 7. Collect Results

```bash
bash server_deploy/collect_results.sh "$LEAKCERT_RUN_ROOT/results/<run_dir>"
```

By default this archive excludes full model weights (`*.safetensors`, `*.bin`,
`checkpoint-*`). Copy the archive back to local:

```bash
scp user@server:/path/to/leakcert_results_*.tgz .
```

## Expected Server Tasks

| task | needs private data? | smoke first | full only when |
|---|---|---|---|
| W2 LCCT/comparable | yes, LCCT/comparable JSONL + target checkpoint | 50-100 prompts | scorer works and `require_real_lcct=true` |
| W4/W5 extraction | target checkpoint | small panel, low token cap | W1 checkpoint is stable |
| W3 utility | optional local dataset/cache | 20 problems | evaluator gives meaningful pass/fail |
| DP sweep | training corpus + per-epsilon checkpoints or ability to train them | one epsilon tiny run | `dp_accounting.json` exists for each epsilon |
| multi-model | training corpus + second model/checkpoint | tiny second-model W1/W4/W5 | checkpoint reload and utility smoke pass |
| certificate calibration | target checkpoint + canary panel | small panel | entropy-capped tables pass audit |

## Cost Controls

- Use `smoke` before `small`, and `small` before `full`.
- Save logs and manifests after every run.
- Do not keep large weights on server unless needed for the next step.
- Archive metrics/config/logs first; copy weights separately only when needed.
- Prefer resuming from existing checkpoints over retraining.
