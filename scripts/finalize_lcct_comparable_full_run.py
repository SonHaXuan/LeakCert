#!/usr/bin/env python3
"""Finalize a completed LCCT-comparable full model run into Updated-Res."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    summary_json = run_dir / "summary.json"
    summary_md = run_dir / "summary.md"
    if not summary_json.exists() or not summary_md.exists():
        raise SystemExit(f"Run is not complete yet: {run_dir}")

    updated = ROOT / "Updated-Res"
    artifacts = updated / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(summary_json, artifacts / "lcct_comparable_model_full_summary.json")
    shutil.copy2(summary_md, artifacts / "lcct_comparable_model_full_summary.md")

    data = json.loads(summary_json.read_text())
    rows = data.get("defenses", {})
    table = [
        "",
        "## Current Full Model Run",
        "",
        f"A full-size local model run was completed on `{data.get('n_prompts')}` comparable LCCT prompts.",
        "",
        "| defense | hits | n | hit rate | refusal |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        table.append(
            f"| {name} | {row.get('hits')} | {row.get('n')} | "
            f"{row.get('hit_rate_pct')}% | {row.get('refusal_rate_pct', 0.0)}% |"
        )
    doc = updated / "lcct_comparable_reimplementation.md"
    text = doc.read_text()
    marker = "## Safe Claim Wording"
    if "## Current Full Model Run" not in text:
        text = text.replace(marker, "\n".join(table) + "\n\n" + marker)
    doc.write_text(text)

    # Rebuild manifest and machine-readable package files.
    run([".venv/bin/python", "scripts/build_updated_res_package.py"])

    scan_cmd = [
        "rg",
        "-n",
        "--hidden",
        "-i",
        r"AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{20,}|sk-test-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}|BEGIN .*PRIVATE|sk-or-v1-[A-Za-z0-9]|OPENROUTER_API_KEY\s*=|/Users/[a-z0-9_]+/|/home/[a-z0-9_.]+/",
        "Updated-Res",
    ]
    scan = subprocess.run(
        scan_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if scan.returncode == 0:
        raise SystemExit("Sensitive-pattern scan failed:\n" + scan.stdout)

    if args.commit:
        run(
            [
                "git",
                "add",
                "Updated-Res",
                "scripts/finalize_lcct_comparable_full_run.py",
            ]
        )
        status = run(["git", "status", "--short"])
        if status.strip():
            env = {
                "GIT_AUTHOR_NAME": "LeakCert Results Bot",
                "GIT_AUTHOR_EMAIL": "leakcert-results@example.invalid",
                "GIT_COMMITTER_NAME": "LeakCert Results Bot",
                "GIT_COMMITTER_EMAIL": "leakcert-results@example.invalid",
            }
            subprocess.check_call(
                ["git", "commit", "-m", "Add LCCT comparable full model results"],
                cwd=ROOT,
                env={**os.environ, **env},
            )
            if args.push:
                subprocess.check_call(["git", "push", "origin", "main"], cwd=ROOT)

    print(
        json.dumps(
            {
                "finalized": str(run_dir),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
