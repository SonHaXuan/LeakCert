#!/usr/bin/env python3
"""Train a lightweight LEAKCERT refusal calibrator from local evaluation data."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.evaluation.workloads import W3RealCompletion
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.refusal import UncertaintyRefusal


def make_panel(cfg: dict):
    n_per_type = cfg["canary"].get("n_eval_per_type", 8)
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=cfg["canary"]["seed"],
    )
    panel = gen.generate_panel(
        include_paraphrase=cfg["canary"].get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    return panel.stratified_subset(n_per_type)


def positive_examples(panel) -> list[str]:
    examples: list[str] = []
    for canary in panel:
        examples.extend(
            [
                canary.secret,
                canary.context + canary.secret,
                canary.full_text,
            ]
        )
    return examples


def negative_examples(
    cfg: dict,
    *,
    max_problems: int,
    batch_size: int,
    temperature: float,
    max_new_tokens: int,
) -> list[str]:
    target_path = cfg["finetune"]["output_dir"]
    model_cfg = cfg.get("model", {})
    target = BackendCompletionService(
        target_path,
        device=model_cfg.get("device", "auto"),
        temperature=temperature,
        top_p=float(model_cfg.get("top_p", 1.0)),
        max_new_tokens=max_new_tokens,
    )
    workload = W3RealCompletion(
        data_path=cfg.get("corpus", {}).get("utility_eval_path"),
        subset=cfg.get("corpus", {}).get("utility_subset", "utility_eval"),
        multilingual=cfg.get("corpus", {}).get("utility_multilingual", False),
    )
    prompts = [s.prompt for s in workload.samples()[:max_problems]]
    outputs = target.complete_many(prompts, n_samples=1, batch_size=batch_size)
    return [result[0].text if result else "" for result in outputs]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-negatives", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--target-refusal-rate", type=float, default=0.01)
    parser.add_argument("--negative-temperature", type=float, default=1.0)
    parser.add_argument("--negative-max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    panel = make_panel(cfg)
    positives = positive_examples(panel)
    negatives = negative_examples(
        cfg,
        max_problems=args.max_negatives,
        batch_size=args.batch_size,
        temperature=args.negative_temperature,
        max_new_tokens=args.negative_max_new_tokens,
    )

    refusal = UncertaintyRefusal(threshold=0.5, use_learned=True)
    refusal.train(positives, negatives)
    threshold = refusal.calibrate_threshold(
        negatives,
        target_refusal_rate=args.target_refusal_rate,
    )
    neg_refusal_rate = refusal.expected_refusal_rate(negatives)
    pos_refusal_rate = refusal.expected_refusal_rate(positives)

    model_path = output_dir / "refusal_calibrator.pkl"
    refusal.save(str(model_path))
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": str(Path(args.config).resolve()),
        "model_path": str(model_path.resolve()),
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "target_refusal_rate": args.target_refusal_rate,
        "negative_temperature": args.negative_temperature,
        "negative_max_new_tokens": args.negative_max_new_tokens,
        "threshold": threshold,
        "positive_refusal_rate": pos_refusal_rate,
        "negative_refusal_rate": neg_refusal_rate,
        "duration_sec": time.time() - started,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (output_dir / "positive_examples_preview.json").write_text(
        json.dumps(positives[:20], indent=2)
    )
    (output_dir / "negative_examples_preview.json").write_text(
        json.dumps(negatives[:20], indent=2)
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
