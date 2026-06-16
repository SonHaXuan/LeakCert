#!/bin/bash
#SBATCH --job-name=leakcert-cert-sweep
#SBATCH --partition=prioritized
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/cert_sweep_%j.out
#SBATCH --error=logs/cert_sweep_%j.err

# Target B (Quality-Evidence runbook): small-budget certificate sweep ONLY.
# CPU-only — reuses the saved kl_estimates.json from eval_certificate.sbatch, so
# it does not compete with GPU jobs (e.g. the 7B training). Re-emits
# certificate_sweep.json with the corrected vacuity flag (raw cert vs H(K))
# and the diagnostic-vs-capped split for the report.

set -e

WORKDIR="$HOME/LeakCert"
KL_JSON="${LEAKCERT_KL_JSON:-$WORKDIR/_run_results/aau_paper_scale/certificate/kl_estimates.json}"
OUT_DIR="${LEAKCERT_SWEEP_OUT:-$WORKDIR/_run_results/aau_paper_scale/certificate_sweep}"

CONTAINER=""
for candidate in \
    "/home/container/pytorch/pytorch_25.09.sif" \
    "/home/container/pytorch/pytorch_25.06.sif" \
    "/home/container/pytorch/pytorch_25.03.sif"; do
    if [[ -f "$candidate" ]]; then CONTAINER="$candidate"; break; fi
done
[[ -n "$CONTAINER" ]] || { echo "ERROR: no PyTorch container found"; exit 1; }

[[ -f "$KL_JSON" ]] || { echo "ERROR: kl_estimates.json missing at $KL_JSON — run eval_certificate.sbatch first"; exit 1; }

echo "=========================================="
echo "LeakCert certificate sweep (CPU-only, Target B)"
echo "Job ID:    $SLURM_JOB_ID"
echo "Node:      $SLURMD_NODENAME"
echo "Container: $CONTAINER"
echo "KL JSON:   $KL_JSON"
echo "Out dir:   $OUT_DIR"
echo "Git:       $(cd $WORKDIR && git rev-parse HEAD)"
echo "=========================================="

mkdir -p "$WORKDIR/logs"

singularity exec \
    --bind "$WORKDIR:$WORKDIR" \
    --bind "$HOME/.local:$HOME/.local" \
    "$CONTAINER" \
    bash -c "
        set -e
        cd $WORKDIR
        pip install --user --quiet -e . 2>/dev/null || true
        python experiments/run_certificate_sweep.py \
            --kl-estimates '$KL_JSON' \
            --output-dir '$OUT_DIR'
    "

echo "Certificate sweep complete -> $OUT_DIR/certificate_sweep.json"
