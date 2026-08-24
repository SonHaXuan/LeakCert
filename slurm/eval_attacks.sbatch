#!/bin/bash
#SBATCH --job-name=leakcert-eval-attacks
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=80G
#SBATCH --time=48:00:00
#SBATCH --output=logs/eval_attacks_%j.out
#SBATCH --error=logs/eval_attacks_%j.err

# W4 (code-secret extraction) + W5 (paraphrase robustness) attack workloads
# against the trained W1 Code-Small target, reduced scale (see config).
# Single GPU; an idle a10 node starts immediately.

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${LEAKCERT_CONFIG:-$WORKDIR/experiments/configs/hpc_eval_attacks.yaml}"

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
echo "LeakCert W4/W5 attack eval"
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
        echo '##### W5 paraphrase robustness #####'
        python experiments/run_w5_paraphrase.py --config '$CONFIG'
        echo '##### W4 code-secret extraction #####'
        python experiments/run_w4_code_secret.py --config '$CONFIG'
    "

echo "W4/W5 attack eval complete."
