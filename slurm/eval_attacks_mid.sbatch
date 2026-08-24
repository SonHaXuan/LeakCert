#!/bin/bash
#SBATCH --job-name=leakcert-eval-mid
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=100G
#SBATCH --time=24:00:00
#SBATCH --output=logs/eval_mid_%j.out
#SBATCH --error=logs/eval_mid_%j.err

# W4/W5 attack-workload eval against the 7B Code-Mid target (target_mid_sub2).
# The scientific complement to the 1.5B eval: does 7B verbatim-leak where 1.5B
# does not? Loads target(7B)+ref(7B) on one L40S (2x~14GB bf16 < 48GB).
#
# Submit:  sbatch slurm/eval_attacks_mid.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/hpc_eval_attacks_mid.yaml"
TARGET="$WORKDIR/checkpoints/target_mid_sub2/checkpoint-20614"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -f "$TARGET/config.json" ]] || { echo "ERROR: 7B target checkpoint missing at $TARGET"; exit 1; }
[[ -d "$WORKDIR/models/qwen2.5-coder-7b" ]] || { echo "ERROR: 7B base (reference) missing at models/qwen2.5-coder-7b"; exit 1; }

echo "=========================================="
echo "LeakCert 7B attack eval (W4/W5/LRT)"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Target:    $TARGET"
echo "Config:    $CONFIG"
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
        echo '--- W5 paraphrase ---'
        python experiments/run_w5_paraphrase.py --config '$CONFIG'
        echo '--- W4 code-secret (+ LRT) ---'
        python experiments/run_w4_code_secret.py --config '$CONFIG'
    "

echo "7B attack eval complete."
