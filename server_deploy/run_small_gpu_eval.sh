#!/usr/bin/env bash
set -euo pipefail

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi missing. This script is intended for NVIDIA GPU servers." >&2
  exit 2
fi

TS="$(date +%Y%m%d_%H%M%S)"
RUN_ROOT="${LEAKCERT_RUN_ROOT:-$HOME/LeakCert_runs}"
OUT="$RUN_ROOT/results/server_small_$TS"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
mkdir -p "$OUT/configs" "$LOG_DIR"
LOG="$LOG_DIR/server_small_gpu_eval_$TS.log"

source .venv/bin/activate

export HF_HOME="${HF_HOME:-$RUN_ROOT/hf_cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$RUN_ROOT/hf_cache}"
export TORCH_HOME="${TORCH_HOME:-$RUN_ROOT/torch_cache}"
export TMPDIR="${TMPDIR:-$RUN_ROOT/tmp}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-10}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-10}"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

MODEL="${LEAKCERT_MODEL:-Salesforce/codegen-350M-mono}"
ROWS="${LEAKCERT_ROWS:-64}"
EPSILONS="${LEAKCERT_EPSILONS:-2,8,16}"
IFS=',' read -r -a EPS_ARRAY <<< "$EPSILONS"

{
  echo "START $(date -Is)"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "OUT=$OUT"
  echo "MODEL=$MODEL"
  echo "ROWS=$ROWS"
  nvidia-smi || true

  for eps in "${EPS_ARRAY[@]}"; do
    eps_clean="$(echo "$eps" | xargs)"
    echo "== DP smoke epsilon $eps_clean =="
    python scripts/run_local_dp_smoke.py \
      --output-dir "$OUT/dp_eps_${eps_clean}" \
      --model "$MODEL" \
      --epsilon "$eps_clean" \
      --rows "$ROWS"
  done

  CKPT="$OUT/dp_eps_8/dp_smoke_checkpoint"
  if [[ ! -d "$CKPT" ]]; then
    CKPT="$OUT/dp_eps_${EPS_ARRAY[0]}/dp_smoke_checkpoint"
  fi

  cat > "$OUT/configs/server_small_eval.yaml" <<YAML
model:
  target_model_small: "$MODEL"
  target_model: "$MODEL"
  device: "cuda"
  max_new_tokens: 96
  temperature: 1.0
  top_p: 1.0
canary:
  n_canaries: 64
  n_eval_per_type: 4
  n_eval: 16
  seed: 51
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
  query_budget: 1000
  batch_size: 8
  test_workers: 8
  run_defenses: [B1, B2, B3, B5, LEAKCERT]
runtime:
  query_budget: 1000
  refusal_threshold: 0.5
  target_refusal_rate: 0.01
output_dir: "$OUT"
seed: 51
YAML

  python scripts/run_phase_a_smoke.py \
    --config "$OUT/configs/server_small_eval.yaml" \
    --output-dir "$OUT/phase_a" \
    --device cuda \
    --batch-size 8 \
    --b7-samples 4 \
    --b7-budget 64 \
    --w3-problems 20

  python scripts/run_phase_b_sweep_smoke.py \
    --config "$OUT/configs/server_small_eval.yaml" \
    --output-dir "$OUT/phase_b" \
    --device cuda \
    --batch-size 8 \
    --temperatures 0.2,0.5,1.5 \
    --top-ps 0.5,0.7,0.9

  python experiments/run_w5_paraphrase.py --config "$OUT/configs/server_small_eval.yaml"
  python scripts/write_run_manifest.py "$OUT"
  echo "END $(date -Is)"
} 2>&1 | tee "$LOG"

echo "Small result: $OUT"
echo "Small log: $LOG"
