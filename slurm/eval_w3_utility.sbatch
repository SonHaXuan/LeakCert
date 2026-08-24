#!/bin/bash
#SBATCH --job-name=leakcert-eval-w3
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:a10:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=logs/eval_w3_%j.out
#SBATCH --error=logs/eval_w3_%j.err

# Target C: W3 utility (pass@1 on HumanEval) for B1/B2/B5/LEAKCERT on the trained
# W1 Code-Small target. Reads a pre-materialised HumanEval JSONL so it needs no
# internet on the compute node. NOTE: pass@1 executes model-generated code inside
# the container sandbox (standard for code-eval benchmarks).

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${LEAKCERT_CONFIG:-$WORKDIR/experiments/configs/hpc_eval_w3.yaml}"

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
[[ -f "$WORKDIR/data/humaneval_w3.jsonl" ]] \
    || { echo "ERROR: HumanEval JSONL missing at data/humaneval_w3.jsonl"; exit 1; }

echo "=========================================="
echo "LeakCert W3 utility eval (Target C)"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "Config:    $CONFIG"
echo "Git:       $(cd $WORKDIR && git rev-parse HEAD)"
echo "=========================================="

mkdir -p "$WORKDIR/logs"

singularity exec --nv \
    --bind "$WORKDIR:$WORKDIR" \
    --bind "$HOME/.local:$HOME/.local" \
    --env HF_HUB_OFFLINE=1 \
    --env HF_DATASETS_OFFLINE=1 \
    "$CONTAINER" \
    bash -c "
        set -e
        cd $WORKDIR
        pip install --user --quiet -e . 2>/dev/null || true
        python experiments/run_w3_real_completion.py --config '$CONFIG'
    "

echo "W3 utility eval complete -> _run_results/hpc_eval_w3/w3"
