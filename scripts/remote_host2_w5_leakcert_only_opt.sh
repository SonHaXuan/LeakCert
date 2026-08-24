#!/usr/bin/env bash
set -euo pipefail

RDIR="${LEAKCERT_REMOTE_ROOT:?set LEAKCERT_REMOTE_ROOT to your remote run directory}"
SRC="$RDIR/source/LeakCert"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
OUT="$RDIR/results/codegen350m_w5_leakcert_only_opt_$RUN_TS"
LOG="$RDIR/logs/codegen350m_w5_leakcert_only_opt_$RUN_TS.log"
CKPT="$RDIR/results/codegen350m_sweep64_20260602_022726/eps_8/dp_smoke_checkpoint"
BASE_MODEL="Salesforce/codegen-350M-mono"

mkdir -p "$OUT/configs" "$RDIR/logs"
cd "$SRC"
source .venv/bin/activate

export OMP_NUM_THREADS=10
export MKL_NUM_THREADS=10
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

cat > "$OUT/configs/codegen350m_w5_leakcert_only_opt.yaml" <<YAML
model:
  target_model_small: "$BASE_MODEL"
  target_model: "$BASE_MODEL"
  device: "cuda"
  max_new_tokens: 96
  temperature: 1.0
  top_p: 1.0
canary:
  n_canaries: 128
  n_eval_per_type: 8
  n_eval: 32
  seed: 45
  include_paraphrase: true
corpus:
  utility_eval_path: ""
  utility_subset: "utility_eval"
  utility_multilingual: false
finetune:
  output_dir: "$CKPT"
finetune_dp:
  output_dir: "$CKPT"
evaluation:
  query_budget: 2000
  batch_size: 8
  test_workers: 8
  run_defenses: [LEAKCERT]
runtime:
  query_budget: 2000
  refusal_threshold: 0.5
  target_refusal_rate: 0.01
output_dir: "$OUT"
seed: 45
YAML

{
  echo "START=$(date -Iseconds)"
  echo "HOST=$(hostname)"
  echo "BASE_MODEL=$BASE_MODEL"
  echo "CKPT=$CKPT"
  nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader || true
  python experiments/run_w5_paraphrase.py --config "$OUT/configs/codegen350m_w5_leakcert_only_opt.yaml"
  python scripts/write_run_manifest.py "$OUT" || true
  echo "END=$(date -Iseconds)"
  echo "OUT=$OUT"
} 2>&1 | tee "$LOG"

ln -sfn "$OUT" "$RDIR/results/codegen350m_w5_leakcert_only_opt_latest"
ln -sfn "$LOG" "$RDIR/logs/codegen350m_w5_leakcert_only_opt_latest.log"
