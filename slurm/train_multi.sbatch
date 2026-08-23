#!/bin/bash
#SBATCH --job-name=leakcert-train-multi
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:4
#SBATCH --cpus-per-task=16
#SBATCH --mem=320G
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
# Train a matched reference with ZERO canaries injected (D1). Combine with
# OUTPUT_DIR to keep it separate from the target checkpoint, e.g.:
#   NO_CANARY=1 OUTPUT_DIR=checkpoints/reference_nocanary sbatch slurm/train_multi.sbatch
[[ -n "$NO_CANARY" ]] && CANARY_ARG="--no-canary"

# Re-inject fresh by default. Set REUSE_INJECTED=1 only to resume an interrupted
# run with an already-correct injected corpus (avoids silently reusing stale data
# when the base corpus changed).
REUSE_ARG=""
[[ -n "$REUSE_INJECTED" ]] && REUSE_ARG="--reuse-injected"

# Override the checkpoint output dir (e.g. to run a second job concurrently
# without clobbering an in-progress run's checkpoints/injected corpus).
OUTDIR_ARG=""
[[ -n "$OUTPUT_DIR" ]] && OUTDIR_ARG="--output-dir $OUTPUT_DIR"

# Override the base (clean) corpus before canary injection, e.g. a subset for a
# cheaper scaled-demonstration target. Canaries are still injected on top, so
# the panel stays identical to the certificate/attack panel.
BASE_CORPUS_ARG=""
[[ -n "$BASE_CORPUS" ]] && BASE_CORPUS_ARG="--base-corpus $BASE_CORPUS"

# Resume a standard (non-DP) run from a prior checkpoint dir after a job died
# mid-run, e.g.:
#   RESUME_FROM=checkpoints/reference_nocanary/checkpoint-6000 \
#     NO_CANARY=1 OUTPUT_DIR=checkpoints/reference_nocanary sbatch slurm/train_multi.sbatch
RESUME_ARG=""
[[ -n "$RESUME_FROM" ]] && RESUME_ARG="--resume-from-checkpoint $RESUME_FROM"

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
    --env TORCH_NCCL_HEARTBEAT_TIMEOUT_SEC=7200 \
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
            $OUTDIR_ARG \
            $BASE_CORPUS_ARG \
            $CANARY_ARG \
            $RESUME_ARG
    "

echo "Multi-GPU training complete (model-key=$MODEL_KEY)."
