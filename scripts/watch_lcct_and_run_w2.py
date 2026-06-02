#!/usr/bin/env python3
"""Watch for a paper-grade LCCT input, then run W2 smoke and full evaluation.

The queue is conservative about evidence quality: it refuses placeholder LCCT
files and refuses synthetic fallback by forcing evaluation.require_real_lcct.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "bin" / "python"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def top_snapshot() -> str:
    return subprocess.run(["top", "-l", "1", "-n", "0"], text=True, capture_output=True).stdout


def cpu_idle_percent(snapshot: str) -> float | None:
    for line in snapshot.splitlines():
        if "CPU usage:" not in line or "% idle" not in line:
            continue
        try:
            return float(line.split("% idle")[0].split(",")[-1].strip())
        except ValueError:
            return None
    return None


def memory_pressure_available_gib() -> float | None:
    try:
        proc = subprocess.run(["memory_pressure"], text=True, capture_output=True, timeout=10)
        total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
    except Exception:
        return None
    pct = None
    for line in proc.stdout.splitlines():
        if "System-wide memory free percentage:" in line:
            try:
                pct = float(line.rsplit(":", 1)[-1].strip().rstrip("%"))
            except ValueError:
                pct = None
            break
    if pct is None:
        return None
    return total / (1024.0 ** 3) * pct / 100.0


def resources_ready(min_idle_pct: float, min_mem_gib: float) -> tuple[bool, dict[str, Any]]:
    snap = top_snapshot()
    idle = cpu_idle_percent(snap)
    mem = memory_pressure_available_gib()
    status = {"cpu_idle_pct": idle, "mem_pressure_available_gib": mem}
    if idle is None or idle < min_idle_pct:
        return False, status | {"reason": "cpu_busy"}
    if mem is None or mem < min_mem_gib:
        return False, status | {"reason": "memory_low"}
    return True, status | {"reason": "ready"}


def inspect_lcct(path: Path, limit: int = 250) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "reason": "missing", "path": str(path)}
    try:
        if path.suffix.lower() == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            rows = obj if isinstance(obj, list) else (
                obj.get("data") or obj.get("examples") or obj.get("samples") or obj.get("items") or []
            )
        else:
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        return {"ok": False, "reason": f"parse_error: {exc}", "path": str(path)}
    if not isinstance(rows, list):
        return {"ok": False, "reason": "not_a_list_or_jsonl", "path": str(path)}
    sampled = rows[:limit]
    missing_prompt = 0
    missing_secret = 0
    not_paper_grade = 0
    categories = set()
    for row in sampled:
        if not isinstance(row, dict):
            continue
        if row.get("not_paper_grade") or "NOT PAPER-GRADE" in str(row):
            not_paper_grade += 1
        if not row.get("prompt"):
            missing_prompt += 1
        if not (row.get("secret") or row.get("expected_secret")):
            missing_secret += 1
        meta = row.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("category"):
            categories.add(str(meta["category"]))
        if row.get("category"):
            categories.add(str(row["category"]))
    ok = bool(rows) and not missing_prompt and not missing_secret and not not_paper_grade
    return {
        "ok": ok,
        "path": str(path),
        "n_rows": len(rows),
        "sampled_rows": len(sampled),
        "missing_prompt": missing_prompt,
        "missing_secret_or_expected_secret": missing_secret,
        "not_paper_grade_rows": not_paper_grade,
        "categories": sorted(categories),
        "reason": "ok" if ok else "schema_or_quality_blocker",
    }


def write_config(base_cfg: dict[str, Any], output_path: Path, output_dir: Path, max_samples: int | None) -> None:
    cfg = dict(base_cfg)
    cfg["output_dir"] = str(output_dir)
    evaluation = dict(cfg.get("evaluation", {}))
    evaluation["require_real_lcct"] = True
    if max_samples is None:
        evaluation.pop("max_w2_samples", None)
    else:
        evaluation["max_w2_samples"] = max_samples
    cfg["evaluation"] = evaluation
    output_path.write_text(yaml.safe_dump(cfg, sort_keys=False))


def run_step(command: list[str], log_path: Path, threads: int) -> int:
    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": str(threads),
        "MKL_NUM_THREADS": str(threads),
        "VECLIB_MAXIMUM_THREADS": str(threads),
        "NUMEXPR_NUM_THREADS": str(threads),
        "TOKENIZERS_PARALLELISM": "false",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        "PYTHONUNBUFFERED": "1",
    })
    with log_path.open("a") as log:
        log.write(f"\n===== START {now()} =====\n")
        log.write(" ".join(command) + "\n")
        proc = subprocess.run(command, cwd=REPO, env=env, text=True, stdout=log, stderr=subprocess.STDOUT)
        log.write(f"===== END rc={proc.returncode} {now()} =====\n")
    return proc.returncode


def write_manifest(run_dir: Path) -> None:
    files = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            files.append({"path": str(path.relative_to(run_dir)), "size": path.stat().st_size})
    (run_dir / "manifest.json").write_text(json.dumps({"created_at": now(), "files": files}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--queue-dir", required=True)
    parser.add_argument("--poll-sec", type=int, default=300)
    parser.add_argument("--min-cpu-idle-pct", type=float, default=15.0)
    parser.add_argument("--min-mem-gib", type=float, default=120.0)
    parser.add_argument("--threads", type=int, default=max(os.cpu_count() - 4, 8))
    args = parser.parse_args()

    queue_dir = Path(args.queue_dir)
    logs_dir = queue_dir / "logs"
    cfg_dir = queue_dir / "configs"
    queue_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    status_path = queue_dir / "watch_status.jsonl"

    while True:
        cfg_path = Path(args.config)
        cfg = yaml.safe_load(cfg_path.read_text())
        lcct_path = Path(cfg.get("corpus", {}).get("lcct_path", "")).expanduser()
        lcct_status = inspect_lcct(lcct_path)
        ready, resource_status = resources_ready(args.min_cpu_idle_pct, args.min_mem_gib)
        status_path.open("a").write(json.dumps({
            "timestamp": now(),
            "lcct": lcct_status,
            "resources": resource_status,
        }) + "\n")

        if not lcct_status["ok"] or not ready:
            time.sleep(args.poll_sec)
            continue

        shutil.copy2(cfg_path, cfg_dir / "source_config.yaml")
        metadata = {
            "started_at": now(),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "source_config": str(cfg_path),
            "lcct": lcct_status,
            "threads": args.threads,
            "resource_status_at_start": resource_status,
        }
        (queue_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        smoke_cfg = cfg_dir / "w2_lcct_smoke.yaml"
        full_cfg = cfg_dir / "w2_lcct_full.yaml"
        write_config(cfg, smoke_cfg, queue_dir / "w2_lcct_smoke", max_samples=100)
        write_config(cfg, full_cfg, queue_dir / "w2_lcct_full", max_samples=None)

        smoke_rc = run_step(
            [str(PYTHON), "experiments/run_w2_lcct.py", "--config", str(smoke_cfg)],
            logs_dir / "w2_lcct_smoke.log",
            args.threads,
        )
        if smoke_rc != 0:
            status_path.open("a").write(json.dumps({"timestamp": now(), "step": "smoke", "returncode": smoke_rc}) + "\n")
            write_manifest(queue_dir)
            return smoke_rc

        full_rc = run_step(
            [str(PYTHON), "experiments/run_w2_lcct.py", "--config", str(full_cfg)],
            logs_dir / "w2_lcct_full.log",
            args.threads,
        )
        status_path.open("a").write(json.dumps({"timestamp": now(), "step": "full", "returncode": full_rc}) + "\n")
        write_manifest(queue_dir)
        return full_rc


if __name__ == "__main__":
    raise SystemExit(main())
