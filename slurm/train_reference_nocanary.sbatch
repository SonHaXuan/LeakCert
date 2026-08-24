#!/bin/bash
#SBATCH --job-name=leakcert-train-refD1
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=48:00:00
#SBATCH --output=logs/train_refD1_%j.out
#SBATCH --error=logs/train_refD1_%j.err

# D1 reference model: SAME corpus / SAME hyperparams as checkpoints/target_small,
# but ZERO canaries injected. This is the matched reference for separating true
# memorization from generic fine-tuning shift (reference-model control, item D1).
#
# Differs from slurm/train_small.sbatch ONLY by:
#   --no-canary       (skip generation+injection, train on clean corpus)
#   --output-dir checkpoints/reference_nocanary
#
# Prereqs: same as train_small (download_model + build_corpus already done).
# Submit with:  sbatch slurm/train_reference_nocanary.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/hpc_paper_scale.yaml"
OUTDIR="checkpoints/reference_nocanary"

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
echo "LeakCert D1 — reference (no-canary) 1.5B"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "Output:    $OUTDIR"
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
            --model-key small \
            --no-canary \
            --output-dir '$OUTDIR'
    "

echo "D1 reference (no-canary) complete: $WORKDIR/$OUTDIR"
