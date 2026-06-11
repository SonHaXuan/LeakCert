#!/bin/bash
#SBATCH --job-name=leakcert-lrt-fp
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:a10:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=80G
#SBATCH --time=04:00:00
#SBATCH --output=logs/lrt_fp_%j.out
#SBATCH --error=logs/lrt_fp_%j.err

# MIA false-positive control for the A-greedy-LRT attack (Table 11).
# Runs the SPRT attacker on a held-out NON-MEMBER panel (different generator
# seed -> canaries the target never trained on). Detection rate here == the
# false positive rate, the missing control for the membership-detection claim.

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${LEAKCERT_CONFIG:-$WORKDIR/experiments/configs/aau_eval_attacks.yaml}"
NONMEMBER_SEED="${NONMEMBER_SEED:-999}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.06.sif" \
    "/home/container/pytorch/pytorch_25.03.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }
[[ -d "$WORKDIR/checkpoints/target_small" ]] || { echo "ERROR: target checkpoint missing"; exit 1; }

echo "=========================================="
echo "LeakCert LRT FP-control (non-member seed=$NONMEMBER_SEED)"
echo "Job ID: $SLURM_JOB_ID  Node: $SLURMD_NODENAME"
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
        python experiments/run_lrt_attack.py --config '$CONFIG' --nonmember-seed $NONMEMBER_SEED
    "

echo "LRT FP-control complete."
