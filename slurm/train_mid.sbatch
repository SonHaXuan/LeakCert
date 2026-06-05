#!/bin/bash
#SBATCH --job-name=leakcert-train-mid
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --time=48:00:00
#SBATCH --output=logs/train_mid_%j.out
#SBATCH --error=logs/train_mid_%j.err

# W1 Code-Mid (7B) target: generate canaries -> inject -> fine-tune.
# Uses an A100 (80GB) by default; a 7B full fine-tune is tight on an L40S.
# Produces checkpoints/target_mid + canary_injection_manifest.json.
#
# Submit with:
#   sbatch slurm/train_mid.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/aau_paper_scale.yaml"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -d "$WORKDIR/models/qwen2.5-coder-7b" ]] || { echo "ERROR: base model missing — run download_model.sbatch"; exit 1; }
[[ -f "$WORKDIR/data/code_corpus.jsonl" ]]  || { echo "ERROR: corpus missing — run build_corpus.sbatch"; exit 1; }

echo "=========================================="
echo "LeakCert W1 — Code-Mid (7B) target"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "=========================================="

mkdir -p "$WORKDIR/logs"

singularity exec --nv \
    --bind "$WORKDIR:$WORKDIR" \
    --bind "$HOME/.local:$HOME/.local" \
    --env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    "$CONTAINER" \
    bash -c "
        set -e
        cd $WORKDIR
        python3 -c \"import torch; print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0))\"
        pip install --user --quiet -e . 2>/dev/null || true
        python3 -u scripts/prepare_and_train_target.py \
            --config '$CONFIG' \
            --model-key mid
    "

echo "Code-Mid target complete: $WORKDIR/checkpoints/target_mid"
