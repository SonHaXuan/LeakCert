#!/bin/bash
#SBATCH --job-name=leakcert-train-multi
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:4
#SBATCH --cpus-per-task=16
#SBATCH --mem=160G
#SBATCH --time=72:00:00
#SBATCH --output=logs/train_multi_%j.out
#SBATCH --error=logs/train_multi_%j.err

# Multi-GPU W1 target training via torchrun (HF Trainer DDP).
# Edit the #SBATCH --gres line above to change GPU count/type
# (e.g. gpu:l40s:8 or gpu:a100:8); torchrun auto-detects the count.
#
# Usage:
#   sbatch slurm/train_multi.sbatch              # small (1.5B), default corpus
#   sbatch slurm/train_multi.sbatch mid          # mid (7B)
#   MAX_CANARIES=2000 sbatch slurm/train_multi.sbatch
#
# Note: this is the standard (non-DP) path. DP-SGD/Opacus is single-GPU only.

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/aau_paper_scale.yaml"
MODEL_KEY="${1:-small}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -f "$WORKDIR/data/code_corpus.jsonl" ]] || { echo "ERROR: corpus missing — run build_corpus.sbatch"; exit 1; }

CANARY_ARG=""
[[ -n "$MAX_CANARIES" ]] && CANARY_ARG="--max-canaries $MAX_CANARIES"

# Re-inject fresh by default. Set REUSE_INJECTED=1 only to resume an interrupted
# run with an already-correct injected corpus (avoids silently reusing stale data
# when the base corpus changed).
REUSE_ARG=""
[[ -n "$REUSE_INJECTED" ]] && REUSE_ARG="--reuse-injected"

echo "=========================================="
echo "LeakCert W1 multi-GPU — model-key=$MODEL_KEY"
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
        NGPU=\$(nvidia-smi -L | wc -l)
        echo \"Visible GPUs: \$NGPU\"
        pip install --user --quiet -e . 2>/dev/null || true
        torchrun --standalone --nproc_per_node=\$NGPU \
            scripts/prepare_and_train_target.py \
            --config '$CONFIG' \
            --model-key $MODEL_KEY \
            $REUSE_ARG \
            $CANARY_ARG
    "

echo "Multi-GPU training complete (model-key=$MODEL_KEY)."
