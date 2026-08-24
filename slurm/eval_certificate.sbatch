#!/bin/bash
#SBATCH --job-name=leakcert-eval-cert
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=80G
#SBATCH --time=12:00:00
#SBATCH --output=logs/eval_cert_%j.out
#SBATCH --error=logs/eval_cert_%j.err

# Certificate evaluation against the trained W1 Code-Small target:
# KL estimation over the injected canary panel + Theorems 10/13/7,
# extraction-probability bound (Cor. 18), tightness, prior-misspec, DP comparison.
# Single GPU is enough (no DDP). Writes JSON tables to _run_results/<cfg.output_dir>/certificate.

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${LEAKCERT_CONFIG:-$WORKDIR/experiments/configs/hpc_paper_scale.yaml}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.06.sif" \
    "/home/container/pytorch/pytorch_25.03.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -d "$WORKDIR/checkpoints/target_small" && -f "$WORKDIR/checkpoints/target_small/config.json" ]] \
    || { echo "ERROR: trained target checkpoint missing at checkpoints/target_small"; exit 1; }

echo "=========================================="
echo "LeakCert certificate eval"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "Config:    $CONFIG"
echo "=========================================="

mkdir -p "$WORKDIR/logs"

singularity exec --nv \
    --bind "$WORKDIR:$WORKDIR" \
    --bind "$HOME/.local:$HOME/.local" \
    "$CONTAINER" \
    bash -c "
        set -e
        cd $WORKDIR
        pip install --user --quiet -e . 2>/dev/null || true
        python experiments/compute_certificate.py --config '$CONFIG'
    "

echo "Certificate eval complete."
