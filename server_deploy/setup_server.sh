#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d_%H%M%S)"
RUN_ROOT="${LEAKCERT_RUN_ROOT:-$HOME/LeakCert_runs}"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
mkdir -p "$RUN_ROOT" "$RUN_ROOT/logs" "$RUN_ROOT/results" "$RUN_ROOT/hf_cache" "$RUN_ROOT/tmp" "$LOG_DIR"
LOG="$LOG_DIR/setup_server_$TS.log"

choose_python() {
  if [[ -n "${LEAKCERT_PYTHON:-}" ]]; then
    command -v "$LEAKCERT_PYTHON"
    return
  fi
  for py in python3.12 python3.11; do
    if command -v "$py" >/dev/null 2>&1; then
      command -v "$py"
      return
    fi
  done
  echo "ERROR: Python 3.11 or 3.12 is required for current PyTorch wheels." >&2
  echo "Install python3.12/python3.11 or set LEAKCERT_PYTHON=/path/to/python." >&2
  return 2
}

PYTHON_BIN="$(choose_python)"

{
  echo "START $(date -Is)"
  echo "RUN_ROOT=$RUN_ROOT"
  echo "PYTHON_BIN=$PYTHON_BIN"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  "$PYTHON_BIN" --version

  "$PYTHON_BIN" -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip setuptools wheel

  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU detected; installing CUDA-capable PyTorch if available."
    pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  fi

  pip install -e ".[dev]"

  python - <<'PY'
import json, platform
import torch
info = {
    "python": platform.python_version(),
    "torch": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "cuda_device_count": torch.cuda.device_count(),
}
if torch.cuda.is_available():
    info["cuda_device_name"] = torch.cuda.get_device_name(0)
print(json.dumps(info, indent=2))
PY
  echo "END $(date -Is)"
} 2>&1 | tee "$LOG"

echo "Setup log: $LOG"
