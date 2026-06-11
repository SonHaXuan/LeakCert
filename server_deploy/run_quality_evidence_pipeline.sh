#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-core}"
if [[ "$PROFILE" != "smoke" && "$PROFILE" != "core" && "$PROFILE" != "full" && "$PROFILE" != "post" ]]; then
  echo "Usage: bash server_deploy/run_quality_evidence_pipeline.sh [smoke|core|full|post]" >&2
  exit 2
fi

RUN_ROOT="${LEAKCERT_RUN_ROOT:-$HOME/LeakCert_runs}"
CONFIG="${LEAKCERT_CONFIG:-$RUN_ROOT/configs/server_real_inputs.yaml}"
TS="$(date +%Y%m%d_%H%M%S)"
PIPELINE_DIR="$RUN_ROOT/results/quality_pipeline_$TS"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
LOG="$LOG_DIR/quality_pipeline_$TS.log"

mkdir -p "$PIPELINE_DIR" "$LOG_DIR" "$RUN_ROOT/results" "$RUN_ROOT/tmp"

exec > >(tee -a "$LOG") 2>&1

run_step() {
  echo
  echo "===== $* ====="
  "$@"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

latest_run_dir() {
  local mode="$1"
  find "$RUN_ROOT/results" -maxdepth 1 -type d -name "server_${mode}_*" -print \
    | sort \
    | tail -n 1
}

require_clean_git() {
  if [[ "${LEAKCERT_ALLOW_DIRTY_GIT:-0}" == "1" ]]; then
    echo "Dirty git tree allowed by LEAKCERT_ALLOW_DIRTY_GIT=1"
    return 0
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    git status --short
    die "git tree is not clean; commit/stash local changes or set LEAKCERT_ALLOW_DIRTY_GIT=1 for debugging"
  fi
}

ensure_environment() {
  if [[ ! -x .venv/bin/python || "${LEAKCERT_FORCE_SETUP:-0}" == "1" ]]; then
    run_step bash server_deploy/setup_server.sh
  else
    echo "Using existing .venv"
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python --version
}

install_bundle_if_requested() {
  if [[ -n "${LEAKCERT_DATA_BUNDLE:-}" ]]; then
    [[ -f "$LEAKCERT_DATA_BUNDLE" ]] || die "LEAKCERT_DATA_BUNDLE not found: $LEAKCERT_DATA_BUNDLE"
    run_step python server_deploy/install_data_bundle.py \
      --bundle "$LEAKCERT_DATA_BUNDLE" \
      --run-root "$RUN_ROOT"
  else
    echo "No LEAKCERT_DATA_BUNDLE set; expecting config/data already installed."
  fi
}

validate_inputs() {
  [[ -f "$CONFIG" ]] || die "config missing: $CONFIG"
  local validator
  validator="${LEAKCERT_INPUT_VALIDATOR:-}"
  if [[ -z "$validator" ]]; then
    validator="$(find scripts -maxdepth 1 -type f -name 'validate_*_real_inputs.py' | sort | head -n 1)"
  fi
  [[ -n "$validator" && -f "$validator" ]] || die "input validator script not found"
  set +e
  run_step python "$validator" \
    --config "$CONFIG" \
    --output-dir "$PIPELINE_DIR/input_validation"
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 && "${LEAKCERT_ALLOW_VALIDATION_BLOCKERS:-0}" != "1" ]]; then
    die "input validation failed; refusing to run evidence pipeline"
  fi
  if [[ "$rc" -ne 0 ]]; then
    echo "Input validation reported blockers; continuing because LEAKCERT_ALLOW_VALIDATION_BLOCKERS=1"
  fi
}

run_tests() {
  if [[ "${LEAKCERT_SKIP_TESTS:-0}" == "1" ]]; then
    echo "Skipping tests by LEAKCERT_SKIP_TESTS=1"
    return 0
  fi
  run_step python -m pytest tests -q -p no:cacheprovider
}

collect_run() {
  local run_dir="$1"
  [[ -n "$run_dir" && -d "$run_dir" ]] || die "run directory missing: $run_dir"
  run_step python scripts/write_run_manifest.py "$run_dir"
  run_step bash server_deploy/collect_results.sh "$run_dir"
  echo "$run_dir" >> "$PIPELINE_DIR/run_dirs.txt"
}

run_eval_mode() {
  local mode="$1"
  run_step bash server_deploy/run_server_evaluations.sh "$mode"
  local run_dir
  run_dir="$(latest_run_dir "$mode")"
  [[ -n "$run_dir" ]] || die "could not locate latest server_${mode}_* run directory"
  collect_run "$run_dir"
  printf '%s' "$run_dir" > "$PIPELINE_DIR/latest_${mode}_dir.txt"
}

run_optional_post_analyses() {
  local full_dir="$1"
  [[ -n "$full_dir" && -d "$full_dir" ]] || die "post-analysis full_dir missing: $full_dir"
  local post_dir="$full_dir/post_analysis"
  mkdir -p "$post_dir"

  if [[ "${LEAKCERT_RUN_INFORMATIVE_SWEEP:-0}" == "1" ]]; then
    local kl_path
    kl_path="$(find "$full_dir" -type f -name 'kl_estimates.json' | sort | head -n 1 || true)"
    if [[ -n "$kl_path" ]]; then
      run_step python scripts/run_informative_budget_sweep.py \
        --kl-estimates "$kl_path" \
        --output-dir "$post_dir/informative_budget"
    else
      echo "No kl_estimates.json found under $full_dir; skipping informative sweep."
    fi
  fi

  if [[ "${LEAKCERT_RUN_COMPONENT_ABLATION:-0}" == "1" ]]; then
    local full_cfg="$full_dir/configs/server_full.yaml"
    [[ -f "$full_cfg" ]] || die "full config missing for component ablation: $full_cfg"
    run_step python scripts/run_leakcert_component_ablation.py \
      --config "$full_cfg" \
      --output-dir "$post_dir/component_ablation" \
      --batch-size "${LEAKCERT_COMPONENT_BATCH_SIZE:-32}"
  fi

  run_step python scripts/write_run_manifest.py "$full_dir"
  run_step bash server_deploy/collect_results.sh "$full_dir"
}

write_pipeline_summary() {
  {
    echo "profile=$PROFILE"
    echo "timestamp=$TS"
    echo "run_root=$RUN_ROOT"
    echo "config=$CONFIG"
    echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "log=$LOG"
    echo "pipeline_dir=$PIPELINE_DIR"
    if [[ -f "$PIPELINE_DIR/run_dirs.txt" ]]; then
      echo
      echo "run_dirs:"
      sed 's/^/- /' "$PIPELINE_DIR/run_dirs.txt"
    fi
  } > "$PIPELINE_DIR/summary.txt"
  run_step python scripts/write_run_manifest.py "$PIPELINE_DIR"
}

echo "START $(date -Is)"
echo "PROFILE=$PROFILE"
echo "RUN_ROOT=$RUN_ROOT"
echo "CONFIG=$CONFIG"
echo "PIPELINE_DIR=$PIPELINE_DIR"
echo "LOG=$LOG"
echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || true
df -h "$RUN_ROOT" . 2>/dev/null || true

if [[ "$PROFILE" != "post" ]]; then
  require_clean_git
  ensure_environment
  install_bundle_if_requested
  validate_inputs
  run_tests
  run_eval_mode smoke

  if [[ "$PROFILE" == "core" || "$PROFILE" == "full" ]]; then
    run_eval_mode small
    run_eval_mode full
  fi
else
  ensure_environment
fi

if [[ "$PROFILE" == "full" ]]; then
  full_dir="$(cat "$PIPELINE_DIR/latest_full_dir.txt")"
  run_optional_post_analyses "$full_dir"
elif [[ "$PROFILE" == "post" ]]; then
  full_dir="${LEAKCERT_POST_FULL_DIR:-}"
  [[ -n "$full_dir" ]] || die "set LEAKCERT_POST_FULL_DIR=/path/to/server_full_* for post profile"
  run_optional_post_analyses "$full_dir"
fi

write_pipeline_summary

echo "END $(date -Is)"
echo "Pipeline summary: $PIPELINE_DIR/summary.txt"
echo "Pipeline log: $LOG"
