#!/bin/bash
#SBATCH --job-name=leakcert-lrt-sweep
#SBATCH --partition=prioritized
#SBATCH --gres=gpu:a10:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=80G
#SBATCH --time=12:00:00
#SBATCH --output=logs/lrt_sweep_%j.out
#SBATCH --error=logs/lrt_sweep_%j.err

# (1) Small-budget certificate sweep (CPU, reuses saved kl_estimates.json)
# (2) Standalone A-greedy-LRT attack, Table 11 LRT-only (GPU, SPRT early-stop)

set -e

WORKDIR="$HOME/LeakCert"
CONFIG="${LEAKCERT_CONFIG:-$WORKDIR/experiments/configs/aau_eval_attacks.yaml}"
KL_JSON="${LEAKCERT_KL_JSON:-$WORKDIR/_run_results/aau_paper_scale/certificate/kl_estimates.json}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.06.sif" \
    "/home/container/pytorch/pytorch_25.03.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -f "$KL_JSON" ]] || { echo "ERROR: kl_estimates.json missing — run eval_certificate.sbatch first"; exit 1; }
[[ -d "$WORKDIR/checkpoints/target_small" ]] || { echo "ERROR: target checkpoint missing"; exit 1; }

echo "=========================================="
echo "LeakCert certificate sweep + LRT attack"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "Config:    $CONFIG"
echo "KL JSON:   $KL_JSON"
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
        echo '##### (1) small-budget certificate sweep #####'
        python experiments/run_certificate_sweep.py \
            --kl-estimates '$KL_JSON' \
            --output-dir _run_results/aau_paper_scale/certificate_sweep
        echo '##### (2) A-greedy-LRT attack (Table 11) #####'
        python experiments/run_lrt_attack.py --config '$CONFIG'
    "

echo "Sweep + LRT complete."
