#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${1:-$HOME/LeakCert_runs}"
REPO_DIR="${2:-$RUN_ROOT/source/LeakCert}"
LOG_DIR="$RUN_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ec2_preflight_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG") 2>&1

echo "===== EC2 PREFLIGHT $(date -Iseconds) ====="
echo "host=$(hostname)"
echo "user=$(whoami)"
echo "pwd=$(pwd)"
echo "run_root=$RUN_ROOT"
echo "repo_dir=$REPO_DIR"

echo "===== OS ====="
uname -a || true
if command -v lsb_release >/dev/null 2>&1; then lsb_release -a || true; fi

echo "===== CPU/MEM/DISK ====="
nproc || true
free -h || true
df -h "$RUN_ROOT" || df -h || true

echo "===== GPU ====="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi
else
  echo "nvidia-smi not found"
fi

echo "===== PYTHON ====="
python3 --version || true

echo "===== REPO ====="
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" rev-parse HEAD
  git -C "$REPO_DIR" status --short || true
else
  echo "repo missing at $REPO_DIR"
fi

echo "===== TORCH ====="
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  "$REPO_DIR/.venv/bin/python" - <<'PY'
import json, platform
try:
    import torch
    info = {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }
    print(json.dumps(info, indent=2))
except Exception as exc:
    print("torch_check_error", repr(exc))
PY
else
  echo "venv missing at $REPO_DIR/.venv"
fi

echo "preflight_log=$LOG"
