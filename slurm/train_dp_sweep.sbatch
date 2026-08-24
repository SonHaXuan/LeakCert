#!/bin/bash
#SBATCH --job-name=leakcert-dp
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=48:00:00
#SBATCH --output=logs/train_dp_%A_%a.out
#SBATCH --error=logs/train_dp_%A_%a.err
#SBATCH --array=0-4

# B6 DP-SGD sweep: trains one Code-Small DP target per epsilon in {1,2,4,8,16}
# as a Slurm job array (one array task per epsilon). Each produces
# checkpoints/dp_eps<E>/ with dp_accounting.json.
#
# Submit with:
#   sbatch slurm/train_dp_sweep.sbatch
# Run a single epsilon, e.g. just eps=8 (index 3):
#   sbatch --array=3 slurm/train_dp_sweep.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/hpc_paper_scale.yaml"

EPSILONS=(1 2 4 8 16)
EPS="${EPSILONS[$SLURM_ARRAY_TASK_ID]}"
[[ -n "$EPS" ]] || { echo "ERROR: bad array index $SLURM_ARRAY_TASK_ID"; exit 1; }
OUTDIR="checkpoints/dp_eps${EPS}"

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
echo "LeakCert B6 DP-SGD — epsilon=$EPS -> $OUTDIR"
echo "Array job:  $SLURM_ARRAY_JOB_ID task $SLURM_ARRAY_TASK_ID"
echo "Node:       $SLURMD_NODENAME"
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
        python3 -c \"import torch; print('CUDA:', torch.cuda.is_available())\"
        pip install --user --quiet -e . opacus 2>/dev/null || true
        python3 -u scripts/prepare_and_train_target.py \
            --config '$CONFIG' \
            --model-key small \
            --dp-epsilon $EPS \
            --output-dir '$OUTDIR'
    "

echo "DP target eps=$EPS complete: $WORKDIR/$OUTDIR"
