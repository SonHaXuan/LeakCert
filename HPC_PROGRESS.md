# LeakCert HPC Training & Evaluation Progress

## Server Connection

| Field | Value |
|---|---|
| Host | `ai-fe02.srv.aau.dk` |
| Username | `tungkvt@cs.aau.dk` |
| Password | *(stored separately — see HPC_CONNECTION.txt)* |
| Method | Python `paramiko` SSH (no sshpass needed on Windows) |

---

## Models on Server (`~/LeakCert/`)

| Path | Size | Description |
|---|---|---|
| `models/qwen2.5-coder-1.5b` | ~3GB | Base 1.5B model (reference) |
| `models/qwen2.5-coder-7b` | ~14GB | Base 7B model (reference) |
| `checkpoints/target_small/` | 25GB | Fine-tuned 1.5B — W1 target (complete) |
| `checkpoints/target_mid_sub2/checkpoint-20614/` | 29GB | Fine-tuned 7B — 1 epoch on 700-doc corpus |
| `checkpoints/target_mid_sub/` | 29GB | Partial 7B — step 3000 only (kept for reference) |

---

## Training History

| Job | Model | Status | Notes |
|---|---|---|---|
| 952566 | 7B | FAILED (OOM at step 3000) | NCCL timeout + FSDP checkpoint OOM |
| 998571 | 7B | FAILED (OOM + disk quota) | Corpus too large (7500 docs) + checkpoint writes |
| 999526 | 7B | **COMPLETED** (54h) | 700-doc corpus, 1 epoch, loss 0.044, saved at step 20614 |

### Key Fixes Applied (in `leakcert/model/fine_tuner.py`)
1. `SHARDED_STATE_DICT` — each rank saves only its own optimizer shard
2. `effective_save_steps = 10_000_000 if cfg.fsdp else cfg.save_steps` — no mid-training checkpoints when FSDP active
3. `timeout=timedelta(hours=2)` in `dist.init_process_group()` — prevents NCCL timeout during tokenization
4. `TORCH_NCCL_HEARTBEAT_TIMEOUT_SEC=7200` in sbatch

### Corpus
- Full corpus: `data/code_corpus.jsonl` (500K docs)
- Subset used: `data/cc_sub700.jsonl` (700 docs → 1.32M sequences → ~21k steps/epoch)

---

## Evaluation Jobs

### Completed ✓
| Job | ID | Result | Time |
|---|---|---|---|
| Certificate 1.5B | 1000855 | COMPLETED | 23m → `_run_results/aau_paper_scale/certificate/` |
| W3 utility 1.5B | 1000857 | COMPLETED | 7m → `_run_results/aau_eval_w3/` |
| Certificate 7B | 1000858 | COMPLETED | 7h 56m → `_run_results/aau_eval_cert_mid/certificate/` |

### 7B Certificate Key Results
- Hoeffding cert: **9.356 nats**
- P(extract) ≤ 100% (cert not tight — expected with 1-epoch training)

### In Progress
| Job | ID | Status | Notes |
|---|---|---|---|
| Attacks W4/W5 1.5B | 1001762 | RUNNING (48h limit) | On `a768-l40s-01`; W5 + W4 path A done, running path B |

### Timed Out (resubmitted)
| Job | ID | Notes |
|---|---|---|
| Attacks W4/W5 1.5B | 1000856 | Hit 24h limit mid-W4 path B; resubmitted as 1001762 |

### Partial W4 Results (from job 1000856)
- W4 path A (B=100 fixed queries): **0% extraction** for B1, B5, LEAKCERT — no simple leakage
- W4 path B (A-adaptive, B=100): LEAKCERT = 1% extraction rate
- B=1000 and B=10000 budgets still running in job 1001762

---

## Slurm Scripts (in `slurm/`)

| Script | GPU | Time | Purpose |
|---|---|---|---|
| `train_multi.sbatch` | 4× L40S | 72h | 7B FSDP training |
| `eval_certificate.sbatch` | 1× GPU | 12h | KL + certificate bounds |
| `eval_attacks.sbatch` | 1× L40S | **48h** | W4/W5 attacks |
| `eval_w3_utility.sbatch` | 1× L40S | 8h | HumanEval pass@1 |

### Submit Examples
```bash
# Training (7B, custom corpus + output)
cd ~/LeakCert
BASE_CORPUS=~/LeakCert/data/cc_sub700.jsonl OUTPUT_DIR=~/LeakCert/checkpoints/target_mid_sub2 sbatch slurm/train_multi.sbatch mid

# Certificate eval (1.5B default)
sbatch slurm/eval_certificate.sbatch

# Certificate eval (7B, override config)
LEAKCERT_CONFIG=experiments/configs/aau_eval_cert_mid.yaml sbatch slurm/eval_certificate.sbatch

# Attacks
sbatch slurm/eval_attacks.sbatch
```

---

## Result Locations on Server

```
~/LeakCert/_run_results/
  aau_paper_scale/certificate/     # 1.5B cert (KL, Theorems 10/13/17)
  aau_eval_w3/w3/                  # W3 HumanEval pass@1
  aau_eval_cert_mid/certificate/   # 7B cert
  aau_eval_attacks/w4/ w5/         # W4/W5 attacks (in progress)
```

---

## Disk Usage on Server (as of 2026-08-12)

```
checkpoints/target_small/          25GB
checkpoints/target_mid_sub/        29GB   (partial, step 3000)
checkpoints/target_mid_sub2/       29GB   (final, step 20614)
models/qwen2.5-coder-1.5b          ~3GB
models/qwen2.5-coder-7b            ~14GB
```
