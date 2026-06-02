#!/usr/bin/env python3
"""Queue heavier W4/W5 evaluation after a stable W1 gate passes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import yaml

from safe_real_pilot import REPO, PYTHON, conflict_processes, memory_free_gib, vm_stat, write_manifest


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def free_to_run(min_free_gib: float) -> tuple[bool, str]:
    conflicts = conflict_processes()
    free_gib = memory_free_gib(vm_stat())
    if conflicts:
        return False, f"conflicts={len(conflicts)} free_gib={free_gib:.2f}"
    if free_gib < min_free_gib:
        return False, f"free_gib={free_gib:.2f} min_free_gib={min_free_gib:.2f}"
    return True, f"free_gib={free_gib:.2f}"


def make_heavy_config(run_dir: Path, *, defenses: list[str], batch_size: int) -> Path:
    src = run_dir / "real_w1_positive_control_stable.yaml"
    if not src.exists():
        raise FileNotFoundError(src)
    cfg = yaml.safe_load(src.read_text())
    cfg.setdefault("evaluation", {})
    cfg["evaluation"]["run_workloads"] = ["W4", "W5"]
    cfg["evaluation"]["run_defenses"] = defenses
    cfg["evaluation"]["batch_size"] = batch_size
    cfg["evaluation"]["adaptive_budgets"] = [25, 50, 100]
    cfg["evaluation"]["query_budget"] = 100
    cfg["evaluation"]["run_attackers_lrt"] = False
    cfg["output_dir"] = str(run_dir)
    out = run_dir / "post_gate_w4_w5_heavy.yaml"
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def w1_completed(suite: dict) -> bool:
    for step in suite.get("steps", []):
        if step.get("name") == "w1_canary_finetune" and step.get("returncode") == 0:
            return True
    return False


def run_step(name: str, command: list[str], run_dir: Path, min_free_gib: float, poll_sec: int) -> dict:
    log = run_dir / f"{name}.log"
    while True:
        ok, reason = free_to_run(min_free_gib)
        if ok:
            break
        with log.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} waiting: {reason}\n")
        time.sleep(poll_sec)

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
    started = time.time()
    with log.open("w") as f:
        proc = subprocess.run(command, cwd=REPO, env=env, text=True, stdout=f, stderr=subprocess.STDOUT)
    return {
        "name": name,
        "status": "completed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "duration_sec": time.time() - started,
        "command": command,
        "log": str(log),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run W4/W5 after W1 direct-probe gate passes.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--poll-sec", type=int, default=30)
    parser.add_argument("--min-free-gib", type=float, default=120.0)
    parser.add_argument("--min-direct-hits", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--defenses",
        nargs="+",
        default=["B1", "B2", "B3", "B5", "LEAKCERT"],
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    queue_log = run_dir / "post_gate_heavy_queue.jsonl"
    started = time.time()

    while True:
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        suite_path = run_dir / "suite_summary.json"
        probe_path = run_dir / "direct_canary_probe.json"
        status = {
            "timestamp": now,
            "event": "poll",
            "suite_exists": suite_path.exists(),
            "probe_exists": probe_path.exists(),
        }
        with queue_log.open("a") as f:
            f.write(json.dumps(status) + "\n")

        if suite_path.exists() and probe_path.exists():
            suite = load_json(suite_path)
            probe = load_json(probe_path)
            hits = int(probe.get("overall", {}).get("n_success", 0))
            total = int(probe.get("overall", {}).get("n_total", 0))
            gate = {
                "timestamp": now,
                "event": "gate",
                "suite_status": suite.get("status"),
                "direct_hits": hits,
                "direct_total": total,
                "min_direct_hits": args.min_direct_hits,
            }
            with queue_log.open("a") as f:
                f.write(json.dumps(gate) + "\n")

            suite_ok = suite.get("status") == "completed" or (
                suite.get("status") == "blocked" and w1_completed(suite) and probe_path.exists()
            )
            if not suite_ok:
                result = {"status": "skipped", "reason": "suite_not_ready", "gate": gate}
                (run_dir / "post_gate_heavy_summary.json").write_text(json.dumps(result, indent=2))
                write_manifest(run_dir)
                return 1
            if hits < args.min_direct_hits:
                result = {"status": "skipped", "reason": "direct_probe_gate_failed", "gate": gate}
                (run_dir / "post_gate_heavy_summary.json").write_text(json.dumps(result, indent=2))
                write_manifest(run_dir)
                return 2

            config = make_heavy_config(run_dir, defenses=args.defenses, batch_size=args.batch_size)
            steps = []
            for name, script in (
                ("post_gate_w4_code_secret", "experiments/run_w4_code_secret.py"),
                ("post_gate_w5_paraphrase", "experiments/run_w5_paraphrase.py"),
            ):
                result = run_step(
                    name,
                    [str(PYTHON), script, "--config", str(config)],
                    run_dir,
                    args.min_free_gib,
                    args.poll_sec,
                )
                steps.append(result)
                if result["returncode"] != 0:
                    break

            subprocess.run([str(PYTHON), "scripts/evaluate_run.py", "--run-dir", str(run_dir)], cwd=REPO, check=False)
            summary = {
                "status": "completed" if all(step["returncode"] == 0 for step in steps) else "failed",
                "duration_sec": time.time() - started,
                "gate": gate,
                "config": str(config),
                "steps": steps,
            }
            (run_dir / "post_gate_heavy_summary.json").write_text(json.dumps(summary, indent=2))
            write_manifest(run_dir)
            return 0 if summary["status"] == "completed" else 1

        time.sleep(args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
