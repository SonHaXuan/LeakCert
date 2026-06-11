# Quality Evidence Server Runbook

This runbook is the server-side checklist for producing review-grade evidence.
It is intentionally gated: do not run full jobs until input validation, smoke
runs, and small runs pass.

The goal is to produce evidence that is traceable, reproducible, and scoped to
what the artifacts actually support.

## 1. Prepare A Private Data Bundle Locally

On the local machine that holds private data or checkpoints:

```bash
cp server_deploy/required_data_manifest.example.json _run_results/server_data_manifest.json
$EDITOR _run_results/server_data_manifest.json
```

Fill in only paths that exist locally:

- training corpus JSONL, required for new W1 training, DP runs, and multi-model runs;
- W2 JSONL, if running W2;
- target checkpoint, if downstream evaluation should skip W1 training;
- optional second checkpoint;
- optional DP checkpoints and accounting files.

Build the private bundle:

```bash
.venv/bin/python server_deploy/make_data_bundle.py \
  --manifest _run_results/server_data_manifest.json \
  --output-dir _run_results/server_payloads
```

Copy the generated `.tgz` to the server. Do not commit it.

## 2. Clone And Configure The Server

On the server:

```bash
git clone https://github.com/SonHaXuan/LeakCert.git
cd LeakCert

export LEAKCERT_RUN_ROOT=/data/LeakCert_runs
export LEAKCERT_PYTHON=python3.12
export LEAKCERT_DATA_BUNDLE=/tmp/leakcert_server_payload_<timestamp>.tgz
```

If `/data` is unavailable, use a large persistent path:

```bash
export LEAKCERT_RUN_ROOT=$HOME/LeakCert_runs
```

## 3. Run The Gated Pipeline

Default run:

```bash
bash server_deploy/run_quality_evidence_pipeline.sh core
```

Profiles:

| profile | purpose | stages |
|---|---|---|
| `smoke` | prove setup and inputs work | preflight, setup, install bundle, validation, tests, smoke |
| `core` | main evidence run | all `smoke` stages, then small, full, collect artifacts |
| `full` | core plus requested optional analyses | all `core` stages plus optional gated post-analyses |
| `post` | run optional post-analyses on an existing full run | no training/evaluation rerun |

Recommended first pass:

```bash
bash server_deploy/run_quality_evidence_pipeline.sh smoke
bash server_deploy/run_quality_evidence_pipeline.sh core
```

## 4. Important Environment Variables

| variable | default | meaning |
|---|---|---|
| `LEAKCERT_RUN_ROOT` | `$HOME/LeakCert_runs` | private run root for data, logs, caches, and results |
| `LEAKCERT_CONFIG` | `$LEAKCERT_RUN_ROOT/configs/server_real_inputs.yaml` | installed server config |
| `LEAKCERT_DATA_BUNDLE` | empty | optional private bundle to install before validation |
| `LEAKCERT_PYTHON` | auto | Python 3.11/3.12 executable used by setup |
| `LEAKCERT_DEVICE` | `cuda` if available, else `cpu` | device passed to configs |
| `LEAKCERT_THREADS` | `12` on CUDA hosts | CPU thread limit |
| `LEAKCERT_RUN_W1` | `0` | set to `1` to train W1 if checkpoint is missing |
| `LEAKCERT_ALLOW_VALIDATION_BLOCKERS` | `0` | set to `1` only for exploratory runs |
| `LEAKCERT_ALLOW_DIRTY_GIT` | `0` | set to `1` only for local debugging |
| `LEAKCERT_SKIP_TESTS` | `0` | set to `1` only when tests were already run on the same commit |
| `LEAKCERT_RUN_INFORMATIVE_SWEEP` | `0` | optional post-analysis from saved KL estimates |
| `LEAKCERT_RUN_COMPONENT_ABLATION` | `0` | optional heavy component ablation after a full run |
| `LEAKCERT_POST_FULL_DIR` | empty | full run directory for `post` profile |

## 5. Core Evidence Targets

### Target A: Full W4/W5 Replication

Run W4/W5 at the full config produced by `run_server_evaluations.sh full`:

- `n_eval_per_type=283`;
- `n_eval=1132`;
- query budget `10000`;
- W2 max prompts `4832`;
- W4/W5 output with per-mode and per-type rates;
- raw audit rows if they do not contain private strings.

Acceptance gate:

- baseline and method are run on the same checkpoint and panel;
- aggregate W5 confidence interval excludes zero for the improvement;
- per-mode failures are reported, not only the aggregate.

### Target B: Informative-Budget Certificate

The certificate is only a headline result if it is non-vacuous in a real
setting.

Required outputs:

- `kl_estimates.json`;
- entropy-capped certificate tables;
- informative-budget sweep around `B* = H(K)/C1`;
- entropy-cap audit;
- clear separation between raw diagnostic quantities and capped quantities.

Acceptance gate:

- every reported MI/certificate value is `<= H(K)`;
- at least one real non-zero setting has `0 < capped_cert < H(K)`;
- zero-KL diagnostics are labeled as diagnostics, not headline evidence.

### Target C: Utility Check

Run W3 on the same checkpoint and defense settings used for extraction.

Acceptance gate:

- B1, B5, and the method under test use the same checkpoint;
- refusal rate is reported;
- low absolute utility is framed as checkpoint/model behavior, not hidden.

### Target D: Stress Attacks And Ablations

Run component ablation and attack stress only after the core full run passes.

Acceptance gate:

- each attack/defense has isolated API keys or sessions;
- component ablation uses a large enough panel to support the claim;
- refusal, rate limiting, accounting, and suppression are reported separately.

### Target E: Optional DP And Multi-Model Evidence

Only claim DP or multi-model robustness if corresponding real checkpoints
exist.

Acceptance gate:

- each DP checkpoint has accounting metadata;
- second-model evaluation reloads successfully;
- W3/W4/W5/certificate are run for every checkpoint being claimed.

## 6. Collection And Audit

The pipeline collects each stage with:

```bash
bash server_deploy/collect_results.sh "$LEAKCERT_RUN_ROOT/results/<run_dir>"
```

The archive excludes large model weights by default. Copy archives back to the
local machine for analysis:

```bash
scp user@server:/path/to/leakcert_results_*.tgz .
```

Every run directory must contain:

- copied config;
- command logs;
- git commit;
- input validation output;
- result JSON/JSONL/Markdown;
- entropy-cap audit where certificates are involved;
- `manifest.json` with sizes and SHA-256 hashes.

## 7. Stop Conditions

Stop and fix inputs or code before continuing if any of the following occurs:

- input validation reports missing real corpus, checkpoint, or required W2 rows;
- unit tests fail on the server commit;
- smoke fails;
- small and full results disagree structurally;
- certificate tables exceed the entropy ceiling without capped replacements;
- full run uses placeholder model IDs or synthetic fallback data;
- result metadata points to a dirty git tree.
