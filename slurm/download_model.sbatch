#!/bin/bash
#SBATCH --job-name=leakcert-download
#SBATCH --partition=prioritized
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/download_model_%j.out
#SBATCH --error=logs/download_model_%j.err

# One-time: download the Code-Small (1.5B) and Code-Mid (7B) base models from
# HuggingFace into $WORKDIR/models/. Edit MODELS below to use different bases.
#
# Submit with:
#   export HF_TOKEN="hf_..."   # only needed for gated models
#   sbatch slurm/download_model.sbatch

set -e

WORKDIR="$HOME/LeakCert"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }
echo "Using container: $CONTAINER"

mkdir -p "$WORKDIR/models" "$WORKDIR/logs"

# repo_id -> local dir
SMALL_REPO="Qwen/Qwen2.5-Coder-1.5B"
SMALL_DIR="$WORKDIR/models/qwen2.5-coder-1.5b"
MID_REPO="Qwen/Qwen2.5-Coder-7B"
MID_DIR="$WORKDIR/models/qwen2.5-coder-7b"

singularity exec --nv "$CONTAINER" bash -c "
    set -e
    python3 -c \"
from huggingface_hub import snapshot_download
import os
token = os.environ.get('HF_TOKEN')
for repo, dst in [('$SMALL_REPO', '$SMALL_DIR'), ('$MID_REPO', '$MID_DIR')]:
    print(f'Downloading {repo} -> {dst}')
    snapshot_download(repo, local_dir=dst, token=token)
    print('  done')
\"
"

echo "Models ready:"
echo "  Code-Small: $SMALL_DIR"
echo "  Code-Mid:   $MID_DIR"
