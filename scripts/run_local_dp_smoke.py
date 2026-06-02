#!/usr/bin/env python3
"""Tiny local DP-SGD smoke test.

This intentionally uses a tiny random model and a tiny corpus. It verifies the
DP training path, Opacus accounting, checkpoint save, and checkpoint reload
before any paid EC2 or larger local run.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path

from leakcert.model.backend_model import BackendCompletionService
from leakcert.model.fine_tuner import CanaryFineTuner, FineTuneConfig


def write_corpus(path: Path, n_rows: int) -> None:
    templates = [
        "def add(a, b):\n    return a + b\n",
        "def normalize(text):\n    return text.strip().lower()\n",
        "class Config:\n    debug = False\n",
        "import os\nBASE_DIR = os.getcwd()\n",
    ]
    with path.open("w", encoding="utf-8") as handle:
        for idx in range(n_rows):
            text = templates[idx % len(templates)] * 2
            handle.write(json.dumps({"text": text}) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="hf-internal-testing/tiny-random-gpt2")
    parser.add_argument("--epsilon", type=float, default=8.0)
    parser.add_argument("--delta", type=float, default=1e-5)
    parser.add_argument("--rows", type=int, default=32)
    args = parser.parse_args()

    run_dir = Path(args.output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    corpus = run_dir / "tiny_dp_corpus.jsonl"
    checkpoint = run_dir / "dp_smoke_checkpoint"
    write_corpus(corpus, args.rows)

    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "model": args.model,
        "epsilon_target": args.epsilon,
        "delta": args.delta,
        "rows": args.rows,
        "corpus": str(corpus),
        "checkpoint": str(checkpoint),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    tuner = CanaryFineTuner(FineTuneConfig(
        model_name_or_path=args.model,
        output_dir=str(checkpoint),
        corpus_path=str(corpus),
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=1,
        learning_rate=5e-5,
        warmup_steps=0,
        max_seq_length=64,
        fp16=False,
        torch_dtype="float32",
        use_dp=True,
        dp_epsilon=args.epsilon,
        dp_delta=args.delta,
        dp_max_grad_norm=1.0,
        logging_steps=1,
        save_steps=1000,
    ))
    tuner.train()

    dp_accounting = checkpoint / "dp_accounting.json"
    if not dp_accounting.exists():
        raise RuntimeError(f"Missing DP accounting file: {dp_accounting}")

    service = BackendCompletionService(str(checkpoint), device="cpu", max_new_tokens=8)
    completion = service.complete("def add(a, b):\n    return", n_samples=1)[0].text
    summary = {
        **metadata,
        "dp_accounting": json.loads(dp_accounting.read_text()),
        "checkpoint_reload_ok": True,
        "completion_preview_len": len(completion),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
