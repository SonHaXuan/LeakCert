#!/bin/bash
#SBATCH --job-name=leakcert-posctl-7b
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=100G
#SBATCH --time=12:00:00
#SBATCH --output=logs/posctl_7b_%j.out
#SBATCH --error=logs/posctl_7b_%j.err

# Rebuttal item 1 (ICLR 2027 #42091): positive control for the exposure and
# SPRT instruments on the over-memorized 7B checkpoint. Inference only, no
# training. Answers yZEX W2/Q2, 1VKn Q2, 53pe W4/Q4.
#
#   Step A  exposure AUC, 1,132 member (seed 42) vs 1,132 non-member (seed 999)
#           canaries, 7B target vs 7B base reference
#           -> Updated-Res/artifacts/c1_nonmember_control_7b/
#   Step B  SPRT detection rate on members (TPR)
#   Step C  SPRT detection rate on non-members (FPR, seed 999)
#           -> _run_results/hpc_eval_attacks_mid/lrt/
#   Step D  scripts/summarize_positive_control.py -> table + verdict
#
# Reference note: the only 7B reference available is the BASE 7B model (there is
# no 7B no-canary reference trained on cc_sub700). State this in the paper.
#
# Submit:  sbatch slurm/eval_positive_control_mid.sbatch
# Fastest: submit STEP=A, STEP=B, STEP=C as 3 parallel jobs, then STEP=D (see below).
# Override: TARGET=... CONFIG=... LRT_OUT=... NONMEMBER_SEED=... N_PER_TYPE=...
# AAU server: CONFIG=$HOME/LeakCert/experiments/configs/aau_eval_attacks_mid.yaml \
#             LRT_OUT=_run_results/aau_eval_attacks_mid/lrt sbatch --export=ALL ...

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${CONFIG:-$WORKDIR/experiments/configs/hpc_eval_attacks_mid.yaml}"
TARGET="${TARGET:-$WORKDIR/checkpoints/target_mid_sub2/checkpoint-20614}"
REF="${REF:-$WORKDIR/models/qwen2.5-coder-7b}"
NONMEMBER_SEED="${NONMEMBER_SEED:-999}"
N_PER_TYPE="${N_PER_TYPE:-283}"          # 283 x 4 types = 1,132 per side
C1_OUT="Updated-Res/artifacts/c1_nonmember_control_7b"
LRT_OUT="${LRT_OUT:-_run_results/hpc_eval_attacks_mid/lrt}"
LABEL="base7b"
STEP="${STEP:-all}"                      # all | A | B | C | D (A/B/C are independent: run in parallel)

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
[[ -d "$REF" ]] || { echo "ERROR: 7B base reference missing at $REF"; exit 1; }

echo "=========================================="
echo "LeakCert 7B positive control (exposure AUC + SPRT TPR/FPR)"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Target:    $TARGET"
echo "Reference: $REF  (label=$LABEL)"
echo "Step:      $STEP"
echo "Panels:    member seed 42 / non-member seed $NONMEMBER_SEED, $N_PER_TYPE per type"
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

        if [ '$STEP' = all ] || [ '$STEP' = A ]; then
        echo '--- A: exposure AUC (member vs non-member) ---'
        python3 -u scripts/run_c1_nonmember_control.py \
            --config '$CONFIG' \
            --target '$TARGET' \
            --ref '$REF' \
            --ref-label '$LABEL' \
            --nonmember-seed $NONMEMBER_SEED \
            --n-per-type $N_PER_TYPE \
            --output-dir '$C1_OUT' \
            --device cuda
        fi

        if [ '$STEP' = all ] || [ '$STEP' = B ]; then
        echo '--- B: SPRT on members (TPR) ---'
        python3 -u experiments/run_lrt_attack.py --config '$CONFIG'
        fi

        if [ '$STEP' = all ] || [ '$STEP' = C ]; then
        echo '--- C: SPRT on non-members (FPR) ---'
        python3 -u experiments/run_lrt_attack.py --config '$CONFIG' \
            --nonmember-seed $NONMEMBER_SEED
        fi

        if [ '$STEP' = all ] || [ '$STEP' = D ]; then
        echo '--- D: summary ---'
        python3 scripts/summarize_positive_control.py \
            --c1-summary '$C1_OUT/c1_summary_$LABEL.json' \
            --c1-rows '$C1_OUT/c1_llr_rows_$LABEL.jsonl' \
            --lrt-members '$LRT_OUT/table11_lrt.json' \
            --lrt-nonmembers '$LRT_OUT/table11_lrt_fpcontrol.json' \
            --out-dir '$C1_OUT'
        fi
    "

echo "7B positive control complete. Summary: $WORKDIR/$C1_OUT/positive_control_summary.md"
