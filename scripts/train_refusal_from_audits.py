#!/usr/bin/env python3
"""Train a refusal calibrator from saved W4/W5 audit completions plus W3 negatives."""

from __future__ import annotations

import argparse
import json
import platform
import random
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


def load_audit_examples(
    paths: list[Path], *, max_pos: int, max_neg: int, seed: int
) -> tuple[list[str], list[str]]:
    pos: list[str] = []
    neg: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                completion = (row.get("completion") or "").strip()
                if not completion:
                    continue
                if row.get("hit"):
                    pos.append(completion)
                else:
                    neg.append(completion)
    rng = random.Random(seed)
    rng.shuffle(pos)
    rng.shuffle(neg)
    return pos[:max_pos], neg[:max_neg]


def canary_positive_examples(cfg: dict, *, max_examples: int, seed: int) -> list[str]:
    panel = make_panel(cfg)
    examples: list[str] = []
    for canary in panel:
        examples.extend(
            [canary.secret, canary.context + canary.secret, canary.full_text]
        )
    rng = random.Random(seed)
    rng.shuffle(examples)
    return examples[:max_examples]


def w3_negative_examples(
    cfg: dict,
    *,
    max_problems: int,
    batch_size: int,
    temperature: float,
    max_new_tokens: int,
) -> list[str]:
    model_cfg = cfg.get("model", {})
    target = BackendCompletionService(
        cfg["finetune"]["output_dir"],
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
    prompts = [sample.prompt for sample in workload.samples()[:max_problems]]
    completions = target.complete_many(prompts, n_samples=1, batch_size=batch_size)
    return [(result[0].text if result else "").strip() for result in completions]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--audit", action="append", default=[])
    parser.add_argument("--max-audit-pos", type=int, default=400)
    parser.add_argument("--max-audit-neg", type=int, default=2000)
    parser.add_argument("--max-canary-pos", type=int, default=200)
    parser.add_argument("--max-w3-neg", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--negative-temperature", type=float, default=1.0)
    parser.add_argument("--negative-max-new-tokens", type=int, default=64)
    parser.add_argument("--target-refusal-rate", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=2027)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    audit_pos, audit_neg = load_audit_examples(
        [Path(p) for p in args.audit],
        max_pos=args.max_audit_pos,
        max_neg=args.max_audit_neg,
        seed=args.seed,
    )
    canary_pos = canary_positive_examples(
        cfg, max_examples=args.max_canary_pos, seed=args.seed
    )
    w3_neg = w3_negative_examples(
        cfg,
        max_problems=args.max_w3_neg,
        batch_size=args.batch_size,
        temperature=args.negative_temperature,
        max_new_tokens=args.negative_max_new_tokens,
    )

    positives = [x for x in audit_pos + canary_pos if x]
    negatives = [x for x in audit_neg + w3_neg if x]
    refusal = UncertaintyRefusal(threshold=0.5, use_learned=True)
    refusal.train(positives, negatives)
    threshold = refusal.calibrate_threshold(
        negatives, target_refusal_rate=args.target_refusal_rate
    )
    pos_refusal = refusal.expected_refusal_rate(positives)
    neg_refusal = refusal.expected_refusal_rate(negatives)

    model_path = output_dir / "refusal_calibrator.pkl"
    refusal.save(str(model_path))
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": str(Path(args.config).resolve()),
        "model_path": str(model_path.resolve()),
        "audit_paths": args.audit,
        "n_positive": len(positives),
        "n_positive_audit": len(audit_pos),
        "n_positive_canary": len(canary_pos),
        "n_negative": len(negatives),
        "n_negative_audit": len(audit_neg),
        "n_negative_w3": len(w3_neg),
        "target_refusal_rate": args.target_refusal_rate,
        "threshold": threshold,
        "positive_refusal_rate": pos_refusal,
        "negative_refusal_rate": neg_refusal,
        "duration_sec": time.time() - started,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (output_dir / "positive_preview.json").write_text(
        json.dumps(positives[:30], indent=2)
    )
    (output_dir / "negative_preview.json").write_text(
        json.dumps(negatives[:30], indent=2)
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
