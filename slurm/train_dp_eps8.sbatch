#!/bin/bash
#SBATCH --job-name=leakcert-dp-eps8
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=48:00:00
#SBATCH --output=logs/train_dp_eps8_%j.out
#SBATCH --error=logs/train_dp_eps8_%j.err

# D4 (NDSS 2027 resubmit): ONE real DP-SGD checkpoint at epsilon=8, to replace
# the analytic-only DP table with an empirical DP leakage/utility measurement.
#
# Scope note: DP-SGD is single-GPU only (Opacus, per-sample grads ~2-3x slower),
# so a full-500k / 3-epoch DP run would blow past the 48h wall. We train on the
# 40k subset (data/code_corpus_40k.jsonl, same one the 7B used) with the SAME
# injected canary panel (seed 42) -> 3 epochs is ~40h on one L40S, fits the wall.
# Injection is ON (default path): the DP model must carry the same canaries as
# the non-DP target for a leakage comparison.
#
# Submit:  sbatch slurm/train_dp_eps8.sbatch

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="$WORKDIR/experiments/configs/aau_paper_scale.yaml"
BASE_CORPUS="data/code_corpus_40k.jsonl"
OUTDIR="checkpoints/dp_eps8"

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
[[ -f "$WORKDIR/$BASE_CORPUS" ]] || { echo "ERROR: subset corpus missing at $BASE_CORPUS"; exit 1; }

echo "=========================================="
echo "LeakCert D4 — DP-SGD epsilon=8 (40k subset)"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Corpus:    $BASE_CORPUS"
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
        python3 -c \"import torch; print('CUDA:', torch.cuda.is_available())\"
        pip install --user --quiet -e . opacus 2>/dev/null || true
        python3 -u scripts/prepare_and_train_target.py \
            --config '$CONFIG' \
            --model-key small \
            --dp-epsilon 8 \
            --base-corpus '$BASE_CORPUS' \
            --output-dir '$OUTDIR'
    "

echo "D4 DP-SGD eps=8 complete: $WORKDIR/$OUTDIR (see dp_accounting.json for achieved epsilon)"
