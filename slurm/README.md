# Running LeakCert training on a Slurm HPC cluster

This mirrors the BudgetCoder HPC workflow. It trains the W1 **target
checkpoints** (the artifacts the config calls `TODO_REAL_*_TARGET_CHECKPOINT`)
by generating canaries, injecting them into a code corpus, and fine-tuning.

Pipeline: `download_model` + `build_corpus` → `train_small` / `train_mid` →
optional `train_dp_sweep`. Config: `experiments/configs/hpc_paper_scale.yaml`.

## 0. Copy code to HPC

```bash
rsync -avz --exclude='.venv/' --exclude='models/' --exclude='data/' \
      --exclude='checkpoints/' --exclude='_run_*/' \
  /path/to/LeakCert/  <your-username>@<your-cluster-host>:~/LeakCert/
```
(or `git clone <this-repo-url> ~/LeakCert`)

## 1. Container

Some clusters provide ready Singularity images under `/home/container`. Check:
```bash
ls /home/container/pytorch*.sif /home/container/pytorch/*.sif 2>/dev/null
```
All scripts auto-detect these; no pull step is needed if one exists.

## 2. One-time: models + corpus (no GPU)

```bash
cd ~/LeakCert
export HF_TOKEN="hf_..."          # only needed for gated models/datasets
sbatch slurm/download_model.sbatch   # Qwen2.5-Coder-1.5B + 7B -> models/
sbatch slurm/build_corpus.sbatch     # code corpus -> data/code_corpus.jsonl
```

Corpus size is controlled by env vars read by `build_corpus.sbatch`:
```bash
DATASET=codeparrot/github-code-clean LANGUAGES="Python JavaScript Go" \
MAX_ROWS=4000000 sbatch slurm/build_corpus.sbatch
```
The paper's full ~12B-token corpus is rarely practical; `MAX_ROWS` defaults to
2,000,000 Python documents. Scale up once a small run is validated.

## 3. Train targets (GPU)

```bash
sbatch slurm/train_small.sbatch   # 1.5B -> checkpoints/target_small  (L40S)
sbatch slurm/train_mid.sbatch     # 7B   -> checkpoints/target_mid    (A100)
```
Each writes the checkpoint plus `canary_injection_manifest.json` and
`train_summary.json` into the output dir.

## 4. DP-SGD sweep (B6, optional)

```bash
sbatch slurm/train_dp_sweep.sbatch        # eps in {1,2,4,8,16} as a job array
sbatch --array=3 slurm/train_dp_sweep.sbatch   # just eps=8
```
Each task writes `checkpoints/dp_eps<E>/` with `dp_accounting.json`.

## 5. Monitor

```bash
squeue --me
tail -f logs/train_small_<jobid>.out
```

## Notes

- **DOS line endings:** if you edited these on Windows, run
  `sed -i 's/\r//' slurm/*.sbatch` on the server before `sbatch`, or Slurm
  rejects the script.
- **GPU types:** override the header `--gres=gpu:l40s:1` with `gpu:a100:1`
  (80GB) for headroom. Check availability with `sinfo -o "%P %G %N"`.
- **Resume:** training is not auto-resume; if a job hits the time limit, raise
  `--time` or reduce corpus size / epochs. Pass `--reuse-injected` (already the
  safe default behavior when re-running with the same output dir) to skip
  re-injection.
- **After training:** point the evaluation config at the produced checkpoints, or
  bundle them back with `server_deploy/make_data_bundle.py` for evaluation runs.
- **Base models / corpus:** change the model ids in `download_model.sbatch` and
  the paths in `experiments/configs/hpc_paper_scale.yaml` to use different bases.
```
