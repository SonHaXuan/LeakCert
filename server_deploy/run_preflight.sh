#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LEAKCERT_LOG_DIR:-_run_logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/server_preflight_$TS.log"

{
  echo "START $(date -Is)"
  echo "PWD=$PWD"
  echo "USER=$(id -un)"
  echo "HOSTNAME=$(hostname)"
  echo "GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo
  echo "== OS =="
  uname -a
  cat /etc/os-release 2>/dev/null || true
  echo
  echo "== CPU/RAM/DISK =="
  nproc || true
  lscpu 2>/dev/null || true
  free -h || true
  df -h . / /data 2>/dev/null || true
  echo
  echo "== Python =="
  for py in python3.12 python3.11 python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py -> $($py --version 2>&1)"
    fi
  done
  echo
  echo "== GPU =="
  command -v nvidia-smi || true
  nvidia-smi || true
  command -v nvcc || true
  nvcc --version 2>/dev/null || true
  echo
  echo "== Network =="
  python3 - <<'PY' 2>/dev/null || true
import socket
print(socket.gethostbyname(socket.gethostname()))
PY
  echo "END $(date -Is)"
} | tee "$LOG"

echo "Preflight log: $LOG"
