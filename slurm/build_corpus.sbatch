#!/bin/bash
#SBATCH --job-name=leakcert-corpus
#SBATCH --partition=prioritized
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=logs/build_corpus_%j.out
#SBATCH --error=logs/build_corpus_%j.err

# Build the W1 base code corpus from HuggingFace into data/code_corpus.jsonl.
# Tune MAX_ROWS / LANGUAGES for the size you want. The paper's full 12B-token
# corpus is rarely practical; the default is a large but tractable subset.
#
# Submit with:
#   export HF_TOKEN="hf_..."   # only if the dataset is gated
#   sbatch slurm/build_corpus.sbatch

set -e

WORKDIR="$HOME/LeakCert"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.03.sif" \
    "$HOME/containers/pytorch_25.09-py3.sif" \
    "$HOME/containers/pytorch_25.03-py3.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }
echo "Using container: $CONTAINER"

mkdir -p "$WORKDIR/data" "$WORKDIR/logs"

DATASET="${DATASET:-codeparrot/github-code-clean}"
LANGUAGES="${LANGUAGES:-Python}"
MAX_ROWS="${MAX_ROWS:-2000000}"
OUTPUT="$WORKDIR/data/code_corpus.jsonl"

singularity exec --nv \
    --bind "$WORKDIR:$WORKDIR" \
    --bind "$HOME/.local:$HOME/.local" \
    "$CONTAINER" \
    bash -c "
        set -e
        cd $WORKDIR
        pip install --user --quiet -U datasets huggingface_hub 2>/dev/null || true
        python3 -u scripts/build_code_corpus.py \
            --dataset '$DATASET' \
            --languages $LANGUAGES \
            --max-rows $MAX_ROWS \
            --output '$OUTPUT'
    "

echo "Corpus built: $OUTPUT"
echo "Lines: $(wc -l < "$OUTPUT")"
