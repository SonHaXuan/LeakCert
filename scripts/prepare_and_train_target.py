#!/usr/bin/env python3
"""End-to-end W1 target-checkpoint training: canaries -> inject -> fine-tune.

This is the missing glue between the corpus, the canary panel, and the
fine-tuner. It produces a real target checkpoint (the artifact the SP config
calls ``TODO_REAL_SMALL_TARGET_CHECKPOINT`` / ``..._MID_...``) plus the canary
injection manifest needed by every downstream attack/certificate run.

Pipeline (Section 3.2 / Section 4.1):
  1. generate canary panel        (leakcert.canary.generator.CanaryGenerator)
  2. inject into the base corpus   (leakcert.canary.injector.CorpusInjector)
  3. fine-tune (standard or DP)    (leakcert.model.fine_tuner.CanaryFineTuner)
  4. save checkpoint + manifest + run summary

Reads the SP YAML config (see experiments/configs/sp2027_real_inputs_template.yaml
and experiments/configs/aau_paper_scale.yaml).

Examples
--------
# Code-Small (1.5B) standard target
python scripts/prepare_and_train_target.py \
    --config experiments/configs/aau_paper_scale.yaml --model-key small

# Code-Mid (7B) target
python scripts/prepare_and_train_target.py \
    --config experiments/configs/aau_paper_scale.yaml --model-key mid

# DP-SGD variant for the epsilon sweep
python scripts/prepare_and_train_target.py \
    --config experiments/configs/aau_paper_scale.yaml --model-key small \
    --dp-epsilon 8 --output-dir checkpoints/dp_eps8

# Validate wiring without training (build corpus + panel + manifest only)
python scripts/prepare_and_train_target.py \
    --config experiments/configs/aau_paper_scale.yaml --model-key small --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import socket
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.canary.injector import CorpusInjector
from leakcert.canary.types import CanaryPanel
from leakcert.model.fine_tuner import CanaryFineTuner, FineTuneConfig

logger = logging.getLogger("prepare_and_train_target")

# Map FineTuneConfig fields to the YAML finetune-section keys we accept.
_FINETUNE_KEYS = (
    "num_train_epochs",
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "learning_rate",
    "warmup_steps",
    "max_grad_norm",
    "max_seq_length",
    "weight_decay",
    "fp16",
    "torch_dtype",
    "logging_steps",
    "save_steps",
    "save_total_limit",
    "dp_delta",
    "dp_max_grad_norm",
    "dp_noise_multiplier",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="SP YAML config path")
    parser.add_argument("--model-key", choices=["small", "mid"], default="small",
                        help="Which model + finetune section to use (default: small)")
    parser.add_argument("--base-corpus", default=None,
                        help="Override corpus.path (clean code JSONL before injection)")
    parser.add_argument("--base-model", default=None,
                        help="Override the base model id / local path")
    parser.add_argument("--output-dir", default=None,
                        help="Override the checkpoint output dir")
    parser.add_argument("--max-canaries", type=int, default=None,
                        help="Override canary.n_canaries (for smaller runs)")
    parser.add_argument("--dp-epsilon", type=float, default=None,
                        help="Train a DP-SGD variant at this epsilon")
    parser.add_argument("--injected-corpus", default=None,
                        help="Where to write the injected corpus (default: <output>/corpus_with_canaries.jsonl)")
    parser.add_argument("--reuse-injected", action="store_true",
                        help="Reuse an existing injected corpus if present instead of regenerating")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate canaries + inject + write manifest, but skip training")
    return parser.parse_args()


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_base_model(cfg: dict, model_key: str, override: str | None) -> str:
    if override:
        return override
    model = cfg.get("model", {})
    key = "target_model_small" if model_key == "small" else "target_model_mid"
    value = model.get(key)
    if not value or str(value).startswith("TODO"):
        raise SystemExit(
            f"model.{key} is unset or still a TODO placeholder ({value!r}). "
            f"Set it in the config or pass --base-model."
        )
    return value


def build_panel(cfg: dict, max_canaries: int | None) -> CanaryPanel:
    canary = cfg.get("canary", {})
    n_canaries = max_canaries or canary.get("n_canaries", 10_000)
    n_eval = canary.get("n_eval", 1132)
    seed = canary.get("seed", 42)
    n_per_type = canary.get("n_eval_per_type", 283)
    gen = CanaryGenerator(n_canaries=n_canaries, n_eval=n_eval, seed=seed)
    panel = gen.generate_panel(
        include_paraphrase=canary.get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    return panel


def make_finetune_config(
    cfg: dict,
    model_key: str,
    *,
    base_model: str,
    injected_corpus: str,
    output_dir: str,
    dp_epsilon: float | None,
) -> FineTuneConfig:
    section = "finetune" if model_key == "small" else "finetune_mid"
    ft = dict(cfg.get(section, {}))
    seed = cfg.get("seed", 42)

    kwargs: dict = {
        "model_name_or_path": base_model,
        "output_dir": output_dir,
        "corpus_path": injected_corpus,
        "seed": seed,
    }
    for key in _FINETUNE_KEYS:
        if key in ft and ft[key] is not None:
            kwargs[key] = ft[key]

    if dp_epsilon is not None:
        dp = dict(cfg.get("finetune_dp", {}))
        kwargs["use_dp"] = True
        kwargs["dp_epsilon"] = dp_epsilon
        if "dp_delta" in dp:
            kwargs["dp_delta"] = dp["dp_delta"]
        if "dp_max_grad_norm" in dp:
            kwargs["dp_max_grad_norm"] = dp["dp_max_grad_norm"]
        # DP-SGD requires fp32 (the fine-tuner enforces this for the model too).
        kwargs["fp16"] = False
        kwargs["torch_dtype"] = "float32"
    else:
        kwargs["use_dp"] = bool(ft.get("use_dp", False))

    return FineTuneConfig(**kwargs)


def maybe_init_distributed() -> tuple[int, int]:
    """Init the process group when launched under torchrun (WORLD_SIZE>1).

    Returns (rank, world_size). HF Trainer reuses an already-initialized group,
    so calling this before training is safe and lets us guard the one-time
    canary injection to rank 0 with a barrier.
    """
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    rank = int(os.environ.get("RANK", "0"))
    if world_size <= 1:
        return rank, world_size
    import torch
    import torch.distributed as dist

    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if torch.cuda.is_available():
        torch.cuda.set_device(local_rank)
    if not dist.is_initialized():
        dist.init_process_group(backend="nccl" if torch.cuda.is_available() else "gloo")
    return rank, world_size


def barrier(world_size: int) -> None:
    if world_size > 1:
        import torch.distributed as dist

        if dist.is_initialized():
            dist.barrier()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    cfg = load_config(args.config)
    rank, world_size = maybe_init_distributed()

    base_model = resolve_base_model(cfg, args.model_key, args.base_model)

    corpus_cfg = cfg.get("corpus", {})
    base_corpus = args.base_corpus or corpus_cfg.get("path")
    if not base_corpus or str(base_corpus).startswith("TODO"):
        raise SystemExit(
            f"corpus.path is unset or a TODO placeholder ({base_corpus!r}). "
            f"Build one with scripts/build_code_corpus.py or pass --base-corpus."
        )
    if not Path(base_corpus).exists():
        raise SystemExit(f"Base corpus not found: {base_corpus}")

    section = "finetune" if args.model_key == "small" else "finetune_mid"
    output_dir = args.output_dir or cfg.get(section, {}).get("output_dir")
    if not output_dir or str(output_dir).startswith("TODO"):
        raise SystemExit(
            f"{section}.output_dir is unset or a TODO placeholder ({output_dir!r}). "
            f"Set it or pass --output-dir."
        )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    injected_corpus = Path(args.injected_corpus or (out / "corpus_with_canaries.jsonl"))
    manifest_path = out / "canary_injection_manifest.json"

    # ---- 1 & 2: canaries + injection (rank 0 only under multi-GPU) ----------
    # Every torchrun process runs this script; only rank 0 may write the
    # injected corpus/manifest. Other ranks wait at the barrier and then read.
    n_canaries = -1
    if rank == 0:
        panel = build_panel(cfg, args.max_canaries)
        n_canaries = len(panel.canaries)
        logger.info("Generated canary panel: %d canaries", n_canaries)
        if args.reuse_injected and injected_corpus.exists() and manifest_path.exists():
            logger.info("Reusing existing injected corpus: %s", injected_corpus)
        else:
            injector = CorpusInjector(seed=cfg.get("canary", {}).get("seed", 42))
            logger.info("Injecting canaries into %s -> %s", base_corpus, injected_corpus)
            positions = injector.inject_into_dataset(base_corpus, panel, injected_corpus)
            injector.save_manifest(positions, panel, manifest_path)
            logger.info("Wrote injection manifest: %s", manifest_path)
    else:
        logger.info("Rank %d waiting for rank-0 canary injection", rank)
    barrier(world_size)
    if not injected_corpus.exists():
        raise RuntimeError(f"Injected corpus missing after injection: {injected_corpus}")

    # ---- 3: fine-tune config ----------------------------------------------
    ft_config = make_finetune_config(
        cfg, args.model_key,
        base_model=base_model,
        injected_corpus=str(injected_corpus),
        output_dir=str(out),
        dp_epsilon=args.dp_epsilon,
    )

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": args.config,
        "model_key": args.model_key,
        "base_model": base_model,
        "base_corpus": str(base_corpus),
        "injected_corpus": str(injected_corpus),
        "manifest": str(manifest_path),
        "output_dir": str(out),
        "n_canaries": n_canaries,
        "use_dp": ft_config.use_dp,
        "dp_epsilon": args.dp_epsilon,
        "dry_run": args.dry_run,
    }

    summary["world_size"] = world_size

    if args.dry_run:
        if rank == 0:
            summary["status"] = "dry-run (training skipped)"
            (out / "train_summary.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary, indent=2))
        return 0

    # ---- 4: train (HF Trainer auto-enables DDP under torchrun) --------------
    logger.info("Starting fine-tuning: model=%s dp=%s eps=%s world_size=%d",
                base_model, ft_config.use_dp, args.dp_epsilon, world_size)
    tuner = CanaryFineTuner(ft_config)
    tuner.train()

    if rank != 0:
        return 0

    dp_accounting = out / "dp_accounting.json"
    if ft_config.use_dp:
        if not dp_accounting.exists():
            raise RuntimeError(f"DP run finished but {dp_accounting} is missing")
        summary["dp_accounting"] = json.loads(dp_accounting.read_text())

    summary["status"] = "trained"
    (out / "train_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    logger.info("Target checkpoint ready: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
