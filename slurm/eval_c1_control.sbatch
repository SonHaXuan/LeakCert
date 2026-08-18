#!/bin/bash
#SBATCH --job-name=leakcert-c1ctrl
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=04:00:00
#SBATCH --output=logs/c1ctrl_%j.out
#SBATCH --error=logs/c1ctrl_%j.err

# C1 non-member control (NDSS 2027 resubmit). Scores member (seed 42) vs
# non-member (seed 999) canary LLR under a chosen reference model.
#
# Default reference = base 1.5B (the old certificate's ref) -> the
# fine-tuning-shift diagnostic. Override for the D1 reference once trained:
#   REF=checkpoints/reference_nocanary REF_LABEL=nocanary sbatch slurm/eval_c1_control.sbatch
#
# Submit (base ref):  sbatch slurm/eval_c1_control.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/aau_paper_scale.yaml"
REF="${REF:-models/qwen2.5-coder-1.5b}"
REF_LABEL="${REF_LABEL:-base}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -d "$WORKDIR/checkpoints/target_small" ]] || { echo "ERROR: target_small missing"; exit 1; }

echo "=========================================="
echo "LeakCert C1 non-member control"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Reference: $REF  (label=$REF_LABEL)"
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
        pip install --user --quiet -e . 2>/dev/null || true
        python3 -u scripts/run_c1_nonmember_control.py \
            --config '$CONFIG' \
            --ref '$REF' \
            --ref-label '$REF_LABEL' \
            --device cuda
    "

echo "C1 control complete (ref=$REF_LABEL)."
