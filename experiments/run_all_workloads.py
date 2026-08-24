#!/usr/bin/env python3
"""
Master evaluation script — runs all 5 workloads sequentially.

Usage:
  python run_all_workloads.py --config configs/full_scale.yaml
  python run_all_workloads.py --config configs/small_scale.yaml

Assumes W1 (fine-tuning) has already been run and checkpoint exists.
To re-train: python run_w1_canary_finetune.py --config <cfg> --force-retrain
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

SCRIPTS = [
    ("compute_certificate.py", "Certificate computation (Tables 1, 3, 4, 8)"),
    ("run_w4_code_secret.py", "W4: Code-secret extraction (Table 2, Figure 2)"),
    ("run_w5_paraphrase.py", "W5: Paraphrase robustness (Table 6)"),
    ("run_w3_real_completion.py", "W3: Utility evaluation (Table 5)"),
    ("run_w2_lcct.py", "W2: LCCT extraction benchmark"),
]


def run_script(script: str, config: str) -> bool:
    logger.info(f"\n{'='*60}")
    logger.info(f"Running: {script}")
    result = subprocess.run(
        [sys.executable, script, "--config", config],
        cwd=Path(__file__).parent,
    )
    if result.returncode != 0:
        logger.error(f"FAILED: {script} (exit code {result.returncode})")
        return False
    return True


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results"))
    eval_cfg = cfg.get("evaluation", {})
    workloads = eval_cfg.get("run_workloads", ["W1", "W2", "W3", "W4", "W5"])

    # Check checkpoint exists
    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    if not Path(target_path).exists() and not args.skip_train_check:
        logger.error(
            f"Target model not found at {target_path}.\n"
            f"Run first: python run_w1_canary_finetune.py --config {args.config}"
        )
        sys.exit(1)

    success_count = 0
    for script, description in SCRIPTS:
        # Skip W2/W3 if not in workloads list
        skip = False
        for w in ["W2", "W3", "W4", "W5"]:
            if w in script.upper() and w not in workloads:
                skip = True
                break
        if skip:
            logger.info(f"Skipping {script} (not in run_workloads)")
            continue

        logger.info(f"\n>>> {description}")
        if run_script(script, args.config):
            success_count += 1
        elif not args.continue_on_error:
            logger.error("Stopping on failure. Use --continue-on-error to proceed.")
            sys.exit(1)

    # Merge all results into a summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Completed {success_count}/{len(SCRIPTS)} evaluation steps")
    _merge_results(output_dir)


def _merge_results(output_dir: Path) -> None:
    """Merge all result JSON files into a single summary."""
    summary = {}
    for json_file in output_dir.rglob("*.json"):
        try:
            with open(json_file) as f:
                key = "/".join(json_file.parts[-2:])
                summary[key] = json.load(f)
        except Exception:
            pass

    summary_path = output_dir / "full_results_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Full results summary saved to {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all LEAKCERT workloads")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-train-check", action="store_true")
    args = parser.parse_args()
    main(args)
