#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

ROOT="${LEAKCERT_REMOTE_ROOT:?set LEAKCERT_REMOTE_ROOT to your remote run directory}"
SRC="$ROOT/source/LeakCert"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
OUT="$ROOT/results/codegen350m_base_w3_80_$RUN_TS"
LOG="$ROOT/logs/codegen350m_base_w3_80_$RUN_TS.log"

mkdir -p "$OUT/configs" "$ROOT/logs"
cd "$SRC"
source .venv/bin/activate

cat > "$OUT/configs/codegen350m_base_w3_80.yaml" <<YAML
model:
  target_model_small: "Salesforce/codegen-350M-mono"
  target_model: "Salesforce/codegen-350M-mono"
  device: "cuda"
  max_new_tokens: 96
  temperature: 1.0
  top_p: 1.0
canary:
  n_canaries: 64
  n_eval_per_type: 4
  n_eval: 16
  seed: 48
  include_paraphrase: true
corpus:
  utility_eval_path: ""
  utility_subset: "utility_eval"
  utility_multilingual: false
finetune:
  output_dir: "Salesforce/codegen-350M-mono"
evaluation:
  query_budget: 1000
  batch_size: 8
  test_workers: 8
runtime:
  query_budget: 1000
  refusal_threshold: 0.5
  target_refusal_rate: 0.01
output_dir: "$OUT"
seed: 48
YAML

{
  echo "START $(date -Is)"
  nvidia-smi || true
  python scripts/run_phase_a_smoke.py \
    --config "$OUT/configs/codegen350m_base_w3_80.yaml" \
    --output-dir "$OUT/phase_a_w3_80" \
    --device cuda \
    --batch-size 8 \
    --b7-samples 4 \
    --b7-budget 64 \
    --w3-problems 80
  python scripts/write_run_manifest.py "$OUT" || true
  echo "DONE $(date -Is)"
} 2>&1 | tee "$LOG"

printf '\nREMOTE_OUT=%s\nREMOTE_LOG=%s\n' "$OUT" "$LOG"
