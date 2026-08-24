#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-smoke}"
if [[ "$MODE" != "smoke" && "$MODE" != "small" && "$MODE" != "full" ]]; then
  echo "Usage: bash server_deploy/run_server_evaluations.sh [smoke|small|full]" >&2
  exit 2
fi

RUN_ROOT="${LEAKCERT_RUN_ROOT:-$HOME/LeakCert_runs}"
CONFIG="${LEAKCERT_CONFIG:-$RUN_ROOT/configs/server_real_inputs.yaml}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$RUN_ROOT/results/server_${MODE}_$TS"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
LOG="$LOG_DIR/server_${MODE}_eval_$TS.log"

mkdir -p "$OUT/configs" "$LOG_DIR" "$RUN_ROOT/tmp" "$RUN_ROOT/hf_cache" "$RUN_ROOT/torch_cache"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config missing: $CONFIG" >&2
  echo "Install a data bundle first or set LEAKCERT_CONFIG=/path/to/server_real_inputs.yaml" >&2
  exit 2
fi

source .venv/bin/activate

export HF_HOME="${HF_HOME:-$RUN_ROOT/hf_cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$RUN_ROOT/hf_cache}"
export TORCH_HOME="${TORCH_HOME:-$RUN_ROOT/torch_cache}"
export TMPDIR="${TMPDIR:-$RUN_ROOT/tmp}"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1

if command -v nvidia-smi >/dev/null 2>&1; then
  DEVICE="${LEAKCERT_DEVICE:-cuda}"
  THREADS="${LEAKCERT_THREADS:-12}"
else
  DEVICE="${LEAKCERT_DEVICE:-cpu}"
  THREADS="${LEAKCERT_THREADS:-$(python - <<'PY'
import os
print(max(1, min(16, (os.cpu_count() or 4) - 1)))
PY
)}"
fi
export OMP_NUM_THREADS="$THREADS"
export MKL_NUM_THREADS="$THREADS"

run_step() {
  echo
  echo "===== $* ====="
  "$@"
}

config_value() {
  local cfg="$1"
  local dotted="$2"
  python - "$cfg" "$dotted" <<'PY'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
cur = cfg
for part in sys.argv[2].split("."):
    if not isinstance(cur, dict):
        cur = ""
        break
    cur = cur.get(part, "")
print(cur or "")
PY
}

maybe_train_w1() {
  local cfg="$1"
  local checkpoint
  checkpoint="$(config_value "$cfg" "finetune.output_dir")"
  if [[ -n "$checkpoint" && -d "$checkpoint" && -f "$checkpoint/config.json" ]]; then
    echo "Checkpoint exists: $checkpoint"
    return 0
  fi
  if [[ "${LEAKCERT_RUN_W1:-0}" != "1" ]]; then
    echo "ERROR: checkpoint missing or incomplete: $checkpoint" >&2
    echo "Set LEAKCERT_RUN_W1=1 to train W1 on this server before downstream evaluation." >&2
    return 3
  fi
  run_step python experiments/run_w1_canary_finetune.py --config "$cfg" --force-retrain
}

write_server_config() {
  local src="$1"
  local dst="$2"
  local n_per_type="$3"
  local n_canaries="$4"
  local query_budget="$5"
  local max_w2="$6"
  local max_new_tokens="$7"
  python - "$src" "$dst" "$n_per_type" "$n_canaries" "$query_budget" "$max_w2" "$max_new_tokens" "$DEVICE" "$OUT" <<'PY'
import sys, yaml
src, dst, n_per_type, n_canaries, query_budget, max_w2, max_new_tokens, device, out = sys.argv[1:]
cfg = yaml.safe_load(open(src))
cfg.setdefault("model", {})["device"] = device
cfg["model"]["max_new_tokens"] = int(max_new_tokens)
cfg.setdefault("canary", {})["n_canaries"] = int(n_canaries)
cfg["canary"]["n_eval_per_type"] = int(n_per_type)
cfg["canary"]["n_eval"] = int(n_per_type) * 4
cfg.setdefault("evaluation", {})["query_budget"] = int(query_budget)
cfg["evaluation"]["max_w2_samples"] = int(max_w2)
cfg["evaluation"]["w3_smoke_samples"] = 20
cfg["evaluation"]["batch_size"] = int(cfg["evaluation"].get("batch_size", 8))
cfg["evaluation"]["require_real_lcct"] = True
cfg.setdefault("runtime", {})["query_budget"] = int(query_budget)
cfg["output_dir"] = out
with open(dst, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
PY
}

{
  echo "START $(date -Is)"
  echo "MODE=$MODE"
  echo "RUN_ROOT=$RUN_ROOT"
  echo "CONFIG=$CONFIG"
  echo "OUT=$OUT"
  echo "DEVICE=$DEVICE"
  echo "THREADS=$THREADS"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || true
  free -h 2>/dev/null || true
  df -h "$RUN_ROOT" . 2>/dev/null || true

  cp "$CONFIG" "$OUT/configs/server_real_inputs.original.yaml"

  set +e
  run_step python scripts/validate_real_inputs.py \
    --config "$CONFIG" \
    --output-dir "$OUT/input_validation"
  VALID_RC=$?
  set -e
  if [[ "$VALID_RC" -ne 0 && "$MODE" == "full" && "${LEAKCERT_ALLOW_VALIDATION_BLOCKERS:-0}" != "1" ]]; then
    echo "Input validation failed; refusing full run."
    exit "$VALID_RC"
  elif [[ "$VALID_RC" -ne 0 ]]; then
    echo "Input validation reported blockers; continuing because MODE=$MODE."
    echo "Do not treat this run as full evidence until blockers are resolved."
  fi

  run_step bash server_deploy/run_preflight.sh

  if [[ "$MODE" == "smoke" ]]; then
    SMOKE_CFG="$OUT/configs/server_smoke.yaml"
    write_server_config "$CONFIG" "$SMOKE_CFG" 2 64 250 50 48
    maybe_train_w1 "$SMOKE_CFG"
    run_step python scripts/run_local_dp_smoke.py \
      --output-dir "$OUT/dp_tiny" \
      --model "${LEAKCERT_TINY_MODEL:-hf-internal-testing/tiny-random-gpt2}" \
      --epsilon "${LEAKCERT_EPSILON:-8}" \
      --rows "${LEAKCERT_ROWS:-32}"
    run_step python experiments/run_w2_lcct.py --config "$SMOKE_CFG"
    run_step python experiments/run_w4_code_secret.py --config "$SMOKE_CFG"
    run_step python experiments/run_w5_paraphrase.py --config "$SMOKE_CFG"
    run_step python experiments/compute_certificate.py --config "$SMOKE_CFG"
  elif [[ "$MODE" == "small" ]]; then
    SMALL_CFG="$OUT/configs/server_small.yaml"
    write_server_config "$CONFIG" "$SMALL_CFG" 8 512 1000 500 96
    maybe_train_w1 "$SMALL_CFG"
    run_step python experiments/run_w2_lcct.py --config "$SMALL_CFG"
    run_step python experiments/run_w4_code_secret.py --config "$SMALL_CFG"
    run_step python experiments/run_w5_paraphrase.py --config "$SMALL_CFG"
    run_step python experiments/compute_certificate.py --config "$SMALL_CFG"
  else
    FULL_CFG="$OUT/configs/server_full.yaml"
    write_server_config "$CONFIG" "$FULL_CFG" 283 10000 10000 4832 128
    maybe_train_w1 "$FULL_CFG"
    run_step python experiments/run_w2_lcct.py --config "$FULL_CFG"
    run_step python experiments/run_w4_code_secret.py --config "$FULL_CFG"
    run_step python experiments/run_w5_paraphrase.py --config "$FULL_CFG"
    run_step python experiments/compute_certificate.py --config "$FULL_CFG"
  fi

  run_step python scripts/audit_entropy_caps.py --output-dir "$OUT/entropy_cap_audit"
  run_step python scripts/write_run_manifest.py "$OUT"
  echo "END $(date -Is)"
} 2>&1 | tee "$LOG"

echo "Result dir: $OUT"
echo "Log: $LOG"
