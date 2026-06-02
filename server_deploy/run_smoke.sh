#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d_%H%M%S)"
RUN_ROOT="${LEAKCERT_RUN_ROOT:-$HOME/LeakCert_runs}"
OUT="$RUN_ROOT/results/server_smoke_$TS"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
mkdir -p "$OUT" "$LOG_DIR"
LOG="$LOG_DIR/server_smoke_$TS.log"

source .venv/bin/activate

export HF_HOME="${HF_HOME:-$RUN_ROOT/hf_cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$RUN_ROOT/hf_cache}"
export TORCH_HOME="${TORCH_HOME:-$RUN_ROOT/torch_cache}"
export TMPDIR="${TMPDIR:-$RUN_ROOT/tmp}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-8}"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

{
  echo "START $(date -Is)"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "OUT=$OUT"
  python scripts/run_local_dp_smoke.py \
    --output-dir "$OUT/dp_tiny" \
    --model "${LEAKCERT_TINY_MODEL:-hf-internal-testing/tiny-random-gpt2}" \
    --epsilon "${LEAKCERT_EPSILON:-8}" \
    --rows "${LEAKCERT_ROWS:-32}"
  python scripts/write_run_manifest.py "$OUT"
  echo "END $(date -Is)"
} 2>&1 | tee "$LOG"

echo "Smoke result: $OUT"
echo "Smoke log: $LOG"
