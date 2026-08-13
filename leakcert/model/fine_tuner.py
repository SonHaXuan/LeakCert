"""
Fine-tuner with canary injection support.

Supports:
  - Standard SGD fine-tuning (baseline: B1-B5)
  - DP-SGD fine-tuning via Opacus (baseline B6: ε=8, δ=1e-5)

The fine-tuner follows the W1 workload setup (Section 4.1):
  - 1.5B (Code-Small) or 7B (Code-Mid) causal sequence model
  - 12B-token GitHub corpus with |K|=10^4 canaries injected
  - Each canary appears exactly once
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    TrainingArguments,
    Trainer,
    get_cosine_schedule_with_warmup,
)

logger = logging.getLogger(__name__)


@dataclass
class FineTuneConfig:
    """Configuration for fine-tuning."""

    model_name_or_path: str = "local-code-model-small"
    output_dir: str = "./checkpoints/target_model"
    corpus_path: str = "./data/corpus_with_canaries.jsonl"

    # Training hyperparameters
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-5
    warmup_steps: int = 100
    max_grad_norm: float = 1.0
    max_seq_length: int = 512
    weight_decay: float = 0.01
    fp16: bool = True
    bf16: bool = False
    torch_dtype: str = "auto"
    gradient_checkpointing: bool = False
    # FSDP sharding for large models that don't fit under plain DDP (e.g. 7B on
    # 44GB GPUs). Empty string = off. Typical: "full_shard auto_wrap".
    fsdp: str = ""
    fsdp_transformer_layer_cls_to_wrap: str = ""   # e.g. "Qwen2DecoderLayer"
    # Under FSDP, prefer activation checkpointing via fsdp_config over the
    # TrainingArguments gradient_checkpointing path: the latter adds a redundant
    # AllGather in the backward pass (HF issue #30404), which roughly doubles
    # step time for 7B full-shard. When this is True we disable the TA path.
    fsdp_activation_checkpointing: bool = False
    # Worker count for corpus tokenization (.map). Each worker forks while the
    # model is already resident in CPU RAM, so for large models (7B) a high count
    # multiplies host-RAM use via copy-on-write and OOM-kills the job. Keep low
    # for 7B (e.g. 2); 8 is fine for 1.5B.
    tokenize_num_proc: int = 8

    # DP-SGD parameters (B6)
    use_dp: bool = False
    dp_epsilon: float = 8.0
    dp_delta: float = 1e-5
    dp_max_grad_norm: float = 1.0
    dp_noise_multiplier: Optional[float] = None   # auto-computed if None
    dp_grad_sample_mode: str = "functorch"
    dp_freeze_position_embeddings: bool = True

    # Logging
    logging_steps: int = 50
    save_steps: int = 3000
    save_total_limit: int = 2   # keep only the latest N checkpoints (bounds disk usage)
    eval_steps: int = 500
    seed: int = 42


class TextDataset(Dataset):
    """Simple dataset for sequence-model fine-tuning from a JSONL corpus."""

    def __init__(
        self,
        corpus_path: str,
        tokenizer,
        max_length: int = 512,
        stride: int = 256,
    ):
        self.examples: list[dict] = []
        effective_stride = min(stride, max(0, max_length - 1))
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line.strip())
                text = obj.get("text", "")
                if not text.strip():
                    continue
                enc = tokenizer(
                    text,
                    truncation=True,
                    max_length=max_length,
                    return_overflowing_tokens=True,
                    stride=effective_stride,
                    return_tensors=None,
                )
                for i in range(len(enc["input_ids"])):
                    ids = enc["input_ids"][i]
                    if len(ids) > 10:   # skip very short chunks
                        self.examples.append({"input_ids": ids})

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        return self.examples[idx]


class CanaryFineTuner:
    """
    Fine-tunes a causal LM on a canary-injected corpus.

    Usage
    -----
    config = FineTuneConfig(model_name_or_path="local-code-model-small",
                            use_dp=False)
    tuner = CanaryFineTuner(config)
    tuner.train()
    service = tuner.get_service()
    """

    def __init__(self, config: FineTuneConfig):
        self.config = config
        self.tokenizer = AutoTokenizer.from_pretrained(
            config.model_name_or_path, trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    # ------------------------------------------------------------------
    # Standard fine-tuning
    # ------------------------------------------------------------------

    def train(self) -> None:
        cfg = self.config
        logger.info(f"Fine-tuning {cfg.model_name_or_path} on {cfg.corpus_path}")
        logger.info(f"DP-SGD: {cfg.use_dp}, ε={cfg.dp_epsilon}, δ={cfg.dp_delta}")

        dtype = self._resolve_dtype()
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name_or_path,
            trust_remote_code=True,
            torch_dtype=torch.float32 if cfg.use_dp else dtype,
        )

        collator = DataCollatorForLanguageModeling(
            tokenizer=self.tokenizer, mlm=False
        )

        if cfg.use_dp:
            # DP path runs a manual single-GPU loop on small corpora; the eager
            # in-memory dataset is fine there.
            dataset = TextDataset(cfg.corpus_path, self.tokenizer, cfg.max_seq_length)
            self._train_with_dp(model, dataset, collator)
        else:
            self._train_standard(model, collator)

    def _build_tokenized_dataset(self, args):
        """Tokenize the corpus once into a memory-mapped Arrow dataset.

        Unlike the eager in-memory TextDataset, this:
          - tokenizes in batches with multiple processes (fast), and
          - is memory-mapped from disk, so all DDP ranks share one copy
            (low host RAM) instead of each rank holding the whole corpus.
        Under torchrun the rank-0 process builds the cache inside
        ``main_process_first`` while other ranks wait, then reuse the cache.
        """
        from datasets import load_dataset

        cfg = self.config
        max_len = cfg.max_seq_length
        stride = min(256, max(0, max_len - 1))
        tokenizer = self.tokenizer

        def tokenize_fn(batch):
            enc = tokenizer(
                batch["text"],
                truncation=True,
                max_length=max_len,
                return_overflowing_tokens=True,
                stride=stride,
            )
            return {"input_ids": enc["input_ids"]}

        with args.main_process_first(desc="corpus tokenization"):
            raw = load_dataset("json", data_files=cfg.corpus_path, split="train")
            tokenized = raw.map(
                tokenize_fn,
                batched=True,
                remove_columns=raw.column_names,
                num_proc=cfg.tokenize_num_proc,
                desc="Tokenizing corpus",
            )
        logger.info("Tokenized dataset: %d sequences", len(tokenized))
        return tokenized

    def _train_standard(self, model, collator) -> None:
        cfg = self.config
        extra_args = {}
        # Route activation checkpointing through fsdp_config when requested, and
        # in that case turn OFF the TrainingArguments gradient_checkpointing path
        # (the two together produce a redundant backward AllGather).
        use_ta_grad_ckpt = cfg.gradient_checkpointing and not (
            cfg.fsdp and cfg.fsdp_activation_checkpointing
        )
        if cfg.fsdp:
            extra_args["fsdp"] = cfg.fsdp
            fsdp_config: dict = {}
            if cfg.fsdp_transformer_layer_cls_to_wrap:
                fsdp_config["transformer_layer_cls_to_wrap"] = (
                    cfg.fsdp_transformer_layer_cls_to_wrap
                )
            if cfg.fsdp_activation_checkpointing:
                fsdp_config["activation_checkpointing"] = True
            # Use sharded optimizer state dict so each rank saves only its own
            # shard instead of consolidating the full optimizer state on rank 0.
            # Consolidation requires ~56 GB VRAM for 7B Adam states, which
            # exceeds 48 GB L40S capacity and OOM-kills the checkpoint save.
            fsdp_config["state_dict_type"] = "SHARDED_STATE_DICT"
            extra_args["fsdp_config"] = fsdp_config
        if use_ta_grad_ckpt:
            # non-reentrant checkpointing is required for FSDP compatibility
            extra_args["gradient_checkpointing_kwargs"] = {"use_reentrant": False}
        # FSDP checkpoint saves consolidate the full optimizer state on rank 0
        # (~56 GB for 7B Adam at FP32), exceeding 48 GB L40S VRAM and also
        # writing ~50 GB of checkpoint files that hit disk quota. Skip
        # intermediate saves entirely; the final model is written via
        # trainer.save_model() below, which only saves model weights.
        effective_save_steps = 10_000_000 if cfg.fsdp else cfg.save_steps
        effective_save_limit = 0 if cfg.fsdp else cfg.save_total_limit
        args = TrainingArguments(
            output_dir=cfg.output_dir,
            num_train_epochs=cfg.num_train_epochs,
            per_device_train_batch_size=cfg.per_device_train_batch_size,
            gradient_accumulation_steps=cfg.gradient_accumulation_steps,
            learning_rate=cfg.learning_rate,
            warmup_steps=cfg.warmup_steps,
            weight_decay=cfg.weight_decay,
            max_grad_norm=cfg.max_grad_norm,
            fp16=cfg.fp16,
            bf16=cfg.bf16,
            gradient_checkpointing=use_ta_grad_ckpt,
            logging_steps=cfg.logging_steps,
            save_steps=effective_save_steps,
            save_total_limit=effective_save_limit,
            seed=cfg.seed,
            dataloader_num_workers=2,
            remove_unused_columns=False,
            **extra_args,
        )
        dataset = self._build_tokenized_dataset(args)
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=dataset,
            data_collator=collator,
        )
        trainer.train()
        trainer.save_model(cfg.output_dir)
        self.tokenizer.save_pretrained(cfg.output_dir)
        logger.info(f"Model saved to {cfg.output_dir}")

    def _resolve_dtype(self):
        cfg = self.config
        if cfg.torch_dtype == "float16":
            return torch.float16
        if cfg.torch_dtype == "bfloat16":
            return torch.bfloat16
        if cfg.torch_dtype == "float32":
            return torch.float32
        if torch.cuda.is_available():
            return torch.float16
        return torch.float32

    # ------------------------------------------------------------------
    # DP-SGD fine-tuning (B6 baseline)
    # ------------------------------------------------------------------

    def _train_with_dp(self, model, dataset, collator) -> None:
        """
        DP-SGD via Opacus.
        Implements B6: (ε,δ)-DP fine-tuning as in Abadi et al. [5].

        Key parameters from the study (Section 4.2, B6):
          ε = 8, δ = 1e-5
        """
        try:
            from opacus import PrivacyEngine
        except ImportError:
            raise ImportError(
                "Opacus is required for DP-SGD. Install with: pip install opacus"
            )

        cfg = self.config
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._untie_shared_lm_head_for_dp(model)
        if cfg.dp_freeze_position_embeddings:
            self._freeze_position_embeddings_for_dp(model)
        model = model.to(device)
        model.train()

        # Opacus requires standard (non-HF Trainer) training loop
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=cfg.learning_rate,
            weight_decay=cfg.weight_decay,
        )
        dataloader = DataLoader(
            dataset,
            batch_size=cfg.per_device_train_batch_size,
            shuffle=True,
            collate_fn=collator,
            drop_last=True,
        )

        privacy_engine = PrivacyEngine()
        model, optimizer, dataloader = privacy_engine.make_private_with_epsilon(
            module=model,
            optimizer=optimizer,
            data_loader=dataloader,
            epochs=cfg.num_train_epochs,
            target_epsilon=cfg.dp_epsilon,
            target_delta=cfg.dp_delta,
            max_grad_norm=cfg.dp_max_grad_norm,
            poisson_sampling=False,
            grad_sample_mode=cfg.dp_grad_sample_mode,
        )

        scheduler = get_cosine_schedule_with_warmup(
            optimizer,
            num_warmup_steps=cfg.warmup_steps,
            num_training_steps=cfg.num_train_epochs * len(dataloader),
        )

        model.train()
        global_step = 0
        for epoch in range(cfg.num_train_epochs):
            for batch in dataloader:
                batch = {k: v.to(device) for k, v in batch.items()}
                if "labels" in batch:
                    outputs = model(**batch)
                else:
                    outputs = model(**batch, labels=batch["input_ids"])
                loss = outputs.loss / cfg.gradient_accumulation_steps
                loss.backward()

                if (global_step + 1) % cfg.gradient_accumulation_steps == 0:
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()

                if global_step % cfg.logging_steps == 0:
                    eps = privacy_engine.get_epsilon(cfg.dp_delta)
                    logger.info(
                        f"Step {global_step} | loss={loss.item():.4f} | ε={eps:.4f}"
                    )
                global_step += 1

        # Save
        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        unwrapped = privacy_engine.module if hasattr(privacy_engine, "module") else model
        # Opacus wraps the model; get original
        if hasattr(unwrapped, "_module"):
            unwrapped = unwrapped._module
        unwrapped.save_pretrained(cfg.output_dir)
        self.tokenizer.save_pretrained(cfg.output_dir)

        final_eps = privacy_engine.get_epsilon(cfg.dp_delta)
        logger.info(f"DP training done. Final ε={final_eps:.4f}, δ={cfg.dp_delta}")

        # Save DP accounting metadata
        dp_meta = {"epsilon": final_eps, "delta": cfg.dp_delta,
                   "max_grad_norm": cfg.dp_max_grad_norm}
        with open(os.path.join(cfg.output_dir, "dp_accounting.json"), "w") as f:
            json.dump(dp_meta, f, indent=2)

    def _untie_shared_lm_head_for_dp(self, model) -> None:
        """Opacus per-sample gradients do not handle tied LM head weights reliably."""
        try:
            input_embeddings = model.get_input_embeddings()
            output_embeddings = model.get_output_embeddings()
        except AttributeError:
            return

        if (
            input_embeddings is None
            or output_embeddings is None
            or not hasattr(input_embeddings, "weight")
            or not hasattr(output_embeddings, "weight")
        ):
            return

        input_weight = input_embeddings.weight
        output_weight = output_embeddings.weight
        if input_weight.data_ptr() != output_weight.data_ptr():
            return

        output_embeddings.weight = torch.nn.Parameter(output_weight.detach().clone())
        if hasattr(model.config, "tie_word_embeddings"):
            model.config.tie_word_embeddings = False
        logger.info("Untied shared LM head weights for Opacus DP-SGD compatibility")

    def _freeze_position_embeddings_for_dp(self, model) -> None:
        """Avoid Opacus batch-shape issues on GPT-style learned position embeddings."""
        position_embeddings = None
        if hasattr(model, "transformer") and hasattr(model.transformer, "wpe"):
            position_embeddings = model.transformer.wpe
        elif hasattr(model, "gpt_neox") and hasattr(model.gpt_neox, "embed_positions"):
            position_embeddings = model.gpt_neox.embed_positions
        elif hasattr(model, "model") and hasattr(model.model, "embed_positions"):
            position_embeddings = model.model.embed_positions

        if position_embeddings is None or not hasattr(position_embeddings, "parameters"):
            return

        frozen = 0
        for param in position_embeddings.parameters():
            if param.requires_grad:
                param.requires_grad = False
                frozen += param.numel()
        if frozen:
            logger.info(
                "Froze %d positional-embedding parameters for Opacus DP-SGD compatibility",
                frozen,
            )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_service(self, **kwargs):
        """Return a BackendCompletionService for the fine-tuned model."""
        from .backend_model import BackendCompletionService
        return BackendCompletionService(self.config.output_dir, **kwargs)

    def get_base_service(self, **kwargs):
        """Return a BackendCompletionService for the base (pre-fine-tuning) model."""
        from .backend_model import BackendCompletionService
        return BackendCompletionService(self.config.model_name_or_path, **kwargs)
