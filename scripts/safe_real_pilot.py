#!/usr/bin/env python3
"""Resource-gated tiny real LeakCert suite launcher.

This script is intentionally conservative. It exits before starting model work
when another MPS/model process is active or when memory headroom is too low.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "bin" / "python"
DEFAULT_MODEL_ID = "hf-internal-testing/tiny-random-gpt2"
CONFLICT_MARKERS = (
    "--device mps",
    "scripts/train_barrier.py",
    "scripts/run_evaluation.py",
    "run_full_model_pipeline",
    "run_next_models",
    "ds_resume_mistral_llama",
    "ds_post_queue_mistral_autodan",
    "ds_post_queue_strong_attacks",
)
IGNORE_CONFLICT_MARKERS = (
    "ds_watchdog",
    "watchdog.log",
    "ds_caffeinate",
)
LOCK_PATH = REPO / "_run_results" / "safe_real_pilot.lock"


def run_text(cmd: list[str], *, check: bool = True) -> str:
    result = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=check)
    return result.stdout.strip()


def acquire_lock() -> int | None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(fd, f"pid={os.getpid()} timestamp={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n".encode())
    return fd


def release_lock(fd: int | None) -> None:
    if fd is None:
        return
    os.close(fd)
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def vm_stat() -> dict[str, int]:
    out = run_text(["vm_stat"], check=False)
    stats: dict[str, int] = {}
    page_size = 16_384
    for line in out.splitlines():
        if "page size of" in line:
            page_size = int(line.split("page size of", 1)[1].split("bytes")[0].strip())
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = "".join(ch for ch in raw if ch.isdigit())
        if value:
            stats[key.strip()] = int(value)
    stats["_page_size"] = page_size
    return stats


def memory_free_gib(stats: dict[str, int]) -> float:
    page_size = stats.get("_page_size", 16_384)
    free_pages = stats.get("Pages free", 0) + stats.get("Pages speculative", 0)
    return free_pages * page_size / (1024**3)


def conflict_processes() -> list[str]:
    ps = run_text(["ps", "aux"], check=False)
    current_pid = str(os.getpid())
    conflicts = []
    for line in ps.splitlines():
        if current_pid in line or "safe_real_pilot.py" in line:
            continue
        if any(marker in line for marker in IGNORE_CONFLICT_MARKERS):
            continue
        if any(marker in line for marker in CONFLICT_MARKERS):
            conflicts.append(line)
    return conflicts


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(run_dir: Path) -> None:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append({
                "path": str(path.relative_to(run_dir)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    (run_dir / "manifest.json").write_text(json.dumps(files, indent=2))


def make_corpus(path: Path) -> None:
    templates = [
        "def add(a, b):\n    return a + b\n",
        "class Config:\n    debug = False\n",
        "import os\nBASE_DIR = os.getcwd()\n",
        "def normalize(x):\n    return x.strip().lower()\n",
        "def is_even(x):\n    return x % 2 == 0\n",
    ]
    with path.open("w") as f:
        for i in range(160):
            f.write(json.dumps({"text": templates[i % len(templates)]}) + "\n")


def make_config(run_dir: Path, *, profile: str, model_id: str) -> Path:
    corpus = run_dir / "tiny_corpus.jsonl"
    make_corpus(corpus)
    positive_control = profile in {"positive_control", "positive_control_stable"}
    stable_control = profile == "positive_control_stable"
    is_tiny_model = model_id == DEFAULT_MODEL_ID
    batch_size = 16 if is_tiny_model else 1
    grad_accum = 1 if is_tiny_model else (4 if stable_control else 8)
    config = {
        "model": {
            "target_model": model_id,
            "ref_model": model_id,
            "device": "auto",
            "max_new_tokens": 16,
            "temperature": 0.0,
            "top_p": 1.0,
        },
        "canary": {
            "n_canaries": 64,
            "n_eval_per_type": 4,
            "n_eval": 16,
            "seed": 42,
            "include_paraphrase": True,
            "injection_repeats": 16 if stable_control else (8 if positive_control else 1),
        },
        "corpus": {"path": str(corpus)},
        "finetune": {
            "output_dir": str(run_dir / "target_model"),
            "num_train_epochs": 1 if stable_control else (2 if positive_control else 1),
            "per_device_train_batch_size": batch_size,
            "gradient_accumulation_steps": grad_accum,
            "learning_rate": 2.0e-5 if stable_control else (1.0e-4 if positive_control else 5.0e-5),
            "warmup_steps": 20 if stable_control else 100,
            "max_grad_norm": 0.5 if stable_control else 1.0,
            "weight_decay": 0.01,
            "max_seq_length": 512,
            "fp16": False,
            "torch_dtype": "float32" if stable_control else "auto",
            "use_dp": False,
        },
        "certificate": {
            "delta": 0.01,
            "budgets": [1, 10, 25, 50, 100] if positive_control else [1, 10, 25, 50],
            "n_queries_per_canary": 1,
        },
        "evaluation": {
            "query_budget": 100 if positive_control else 50,
            "adaptive_budgets": [25, 50, 100] if positive_control else [10, 25, 50],
            "batch_size": 16,
            "n_eval_canaries": 16,
            "run_workloads": ["W1"] if stable_control else ["W1", "W4", "W5"],
            "run_defenses": ["B1"],
            "run_attackers": [],
            "run_attackers_lrt": False,
        },
        "runtime": {
            "query_budget": 100 if positive_control else 50,
            "refusal_threshold": 0.5,
            "target_refusal_rate": 0.01,
        },
        "output_dir": str(run_dir),
        "seed": 42,
        "experiment_profile": profile,
        "notes": (
            "Stable positive-control W1-only smoke: float32 training, lower LR, "
            "higher canary exposure, gradient clipping, and direct post-probe."
            if stable_control
            else (
            "Positive-control memorisation stress test: repeated canary exposure, "
            "intended to verify that extraction/certificate metrics show a signal."
            if positive_control
            else "Tiny end-to-end smoke/pilot run."
            )
        ),
    }
    path = run_dir / f"real_w1_{profile}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def metadata(
    run_dir: Path,
    config_path: Path,
    status: str,
    notes: str,
    *,
    profile: str,
    model_id: str,
) -> dict:
    stats = vm_stat()
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "repo": str(REPO),
        "git_commit": run_text(["git", "rev-parse", "HEAD"], check=False),
        "git_status": run_text(["git", "status", "--short", "--branch"], check=False),
        "status": status,
        "notes": notes,
        "run_dir": str(run_dir),
        "config_path": str(config_path),
        "profile": profile,
        "model_id": model_id,
        "python": str(PYTHON),
        "memory_free_gib": round(memory_free_gib(stats), 3),
        "conflict_processes": conflict_processes(),
        "env": {
            "OMP_NUM_THREADS": "16",
            "MKL_NUM_THREADS": "16",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        },
    }


def resource_block_reason(min_free_gib: float) -> str | None:
    conflicts = conflict_processes()
    free_gib = memory_free_gib(vm_stat())
    if conflicts or free_gib < min_free_gib:
        return (
            f"blocked: conflicts={len(conflicts)} free_gib={free_gib:.2f} "
            f"min_free_gib={min_free_gib:.2f}"
        )
    return None


def run_step(
    *,
    name: str,
    command: list[str],
    env: dict[str, str],
    run_dir: Path,
    min_free_gib: float,
) -> dict:
    reason = resource_block_reason(min_free_gib)
    step_log = run_dir / f"{name}.log"
    if reason:
        step_log.write_text(reason + "\n")
        return {"name": name, "status": "blocked", "returncode": 75, "notes": reason}

    start = time.time()
    with step_log.open("w") as f:
        proc = subprocess.run(command, cwd=REPO, env=env, text=True, stdout=f, stderr=subprocess.STDOUT)
    elapsed = time.time() - start
    return {
        "name": name,
        "status": "completed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "duration_sec": elapsed,
        "command": command,
        "log": str(step_log),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely run a tiny real LeakCert suite.")
    parser.add_argument("--min-free-gib", type=float, default=64.0)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--profile",
        choices=["tiny", "positive_control", "positive_control_stable"],
        default="tiny",
        help="tiny preserves the original conservative pilot; positive_control repeats canaries for a labelled stress test.",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    args = parser.parse_args()

    lock_fd = acquire_lock()
    if lock_fd is None:
        print(f"blocked: existing LeakCert safe pilot lock at {LOCK_PATH}")
        return 75

    ts = time.strftime("%Y%m%d_%H%M%S")
    try:
        run_dir = REPO / "_run_results" / f"safe_real_suite_{args.profile}_{ts}"
        run_dir.mkdir(parents=True, exist_ok=False)
        config_path = make_config(run_dir, profile=args.profile, model_id=args.model_id)

        reason = resource_block_reason(args.min_free_gib)
        if reason:
            (run_dir / "metadata.json").write_text(
                json.dumps(
                    metadata(
                        run_dir,
                        config_path,
                        "blocked",
                        reason,
                        profile=args.profile,
                        model_id=args.model_id,
                    ),
                    indent=2,
                )
            )
            write_manifest(run_dir)
            print(reason)
            print(run_dir)
            return 75

        if args.check_only:
            free_gib = memory_free_gib(vm_stat())
            (run_dir / "metadata.json").write_text(
                json.dumps(
                    metadata(
                        run_dir,
                        config_path,
                        "ready",
                        "check-only passed",
                        profile=args.profile,
                        model_id=args.model_id,
                    ),
                    indent=2,
                )
            )
            write_manifest(run_dir)
            print(f"ready: free_gib={free_gib:.2f}")
            print(run_dir)
            return 0

        shutil.copy2(REPO / "experiments" / "configs" / "small_scale.yaml", run_dir / "source_small_scale.yaml")
        env = os.environ.copy()
        env.update({
            "OMP_NUM_THREADS": "16",
            "MKL_NUM_THREADS": "16",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTORCH_ENABLE_MPS_FALLBACK": "1",
            "PYTHONUNBUFFERED": "1",
        })

        configured_workloads = set(yaml.safe_load(open(config_path)).get("evaluation", {}).get("run_workloads", []))
        steps = []
        if "W1" in configured_workloads:
            steps.append((
                "w1_canary_finetune",
                [
                    str(PYTHON),
                    "experiments/run_w1_canary_finetune.py",
                    "--config", str(config_path),
                    "--force-retrain",
                ],
            ))
            steps.append((
                "direct_canary_probe",
                [
                    str(PYTHON),
                    "scripts/direct_canary_probe.py",
                    "--config", str(config_path),
                    "--output", str(run_dir / "direct_canary_probe.json"),
                    "--batch-size", "16",
                ],
            ))
        if "CERT" in configured_workloads:
            steps.append((
                "certificate",
                [
                    str(PYTHON),
                    "experiments/compute_certificate.py",
                    "--config", str(config_path),
                ],
            ))
        if "W4" in configured_workloads:
            steps.append((
                "w4_code_secret",
                [
                    str(PYTHON),
                    "experiments/run_w4_code_secret.py",
                    "--config", str(config_path),
                ],
            ))
        if "W5" in configured_workloads:
            steps.append((
                "w5_paraphrase",
                [
                    str(PYTHON),
                    "experiments/run_w5_paraphrase.py",
                    "--config", str(config_path),
                ],
            ))

        suite_start = time.time()
        step_results = []
        final_code = 0
        for name, command in steps:
            result = run_step(
                name=name,
                command=command,
                env=env,
                run_dir=run_dir,
                min_free_gib=args.min_free_gib,
            )
            step_results.append(result)
            if result["returncode"] != 0:
                final_code = int(result["returncode"])
                break

        suite_status = "completed" if final_code == 0 else step_results[-1]["status"]
        summary = {
            "status": suite_status,
            "returncode": final_code,
            "run_dir": str(run_dir),
            "steps": step_results,
            "duration_sec": time.time() - suite_start,
        }
        (run_dir / "suite_summary.json").write_text(json.dumps(summary, indent=2))

        meta = metadata(
            run_dir,
            config_path,
            suite_status,
            f"returncode={final_code}",
            profile=args.profile,
            model_id=args.model_id,
        )
        meta["suite"] = steps
        meta["runtime_duration_sec"] = summary["duration_sec"]
        meta["returncode"] = final_code
        (run_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
        write_manifest(run_dir)
        print(json.dumps(summary, indent=2))
        return final_code
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
