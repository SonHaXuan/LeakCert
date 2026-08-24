#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="${1:-}"
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  echo "Usage: bash server_deploy/collect_results.sh /path/to/run_dir" >&2
  exit 2
fi

RUN_DIR="$(cd "$RUN_DIR" && pwd)"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${RUN_DIR%/}_artifact_$TS.tgz"

python scripts/write_run_manifest.py "$RUN_DIR" >/dev/null || true

tar -czf "$OUT" \
  --exclude='*.safetensors' \
  --exclude='*.bin' \
  --exclude='*.pt' \
  --exclude='*.pth' \
  --exclude='checkpoint-*' \
  -C "$(dirname "$RUN_DIR")" "$(basename "$RUN_DIR")"

echo "Artifact archive: $OUT"
du -h "$OUT" || true
