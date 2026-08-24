#!/bin/bash
#SBATCH --job-name=leakcert-train-small
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=48:00:00
#SBATCH --output=logs/train_small_%j.out
#SBATCH --error=logs/train_small_%j.err

# W1 Code-Small (1.5B) target: generate canaries -> inject -> fine-tune.
# Produces checkpoints/target_small + canary_injection_manifest.json.
#
# Prereqs: slurm/download_model.sbatch and slurm/build_corpus.sbatch done.
# Submit with:
#   sbatch slurm/train_small.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/hpc_paper_scale.yaml"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -d "$WORKDIR/models/qwen2.5-coder-1.5b" ]] || { echo "ERROR: base model missing — run download_model.sbatch"; exit 1; }
[[ -f "$WORKDIR/data/code_corpus.jsonl" ]]    || { echo "ERROR: corpus missing — run build_corpus.sbatch"; exit 1; }

echo "=========================================="
echo "LeakCert W1 — Code-Small (1.5B) target"
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
            --model-key small
    "

echo "Code-Small target complete: $WORKDIR/checkpoints/target_small"
