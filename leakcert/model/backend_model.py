"""
model backend completion service.

Wraps any causal sequence model from the model backend Hub as a CompletionService.
Supports both the target model (fine-tuned, p_K) and the reference model (base, q_K).

study models:
  Code-Small : local-code-model-small  (1.5B)
  Code-Mid   : local-code-model-mid  (7B)
  Reference  : same architecture, pre-fine-tuning checkpoint
"""

from __future__ import annotations


import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

from .completion_service import CompletionResult, CompletionService


class BackendCompletionService(CompletionService):
    """
    model backend-backed completion service.

    Parameters
    ----------
    model_name_or_path : model backend model ID or local path.
    device             : 'cuda', 'cpu', or 'auto'.
    load_in_8bit       : use bitsandbytes 8-bit quantisation (saves VRAM).
    """

    def __init__(
        self,
        model_name_or_path: str,
        device: str = "auto",
        load_in_8bit: bool = False,
        temperature: float = 1.0,
        top_p: float = 1.0,
        max_new_tokens: int = 128,
        content_filter=None,
        torch_dtype=None,
    ):
        super().__init__(temperature, top_p, max_new_tokens, content_filter)
        self._model_path = model_name_or_path

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path, trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left"

        load_kwargs: dict = {"trust_remote_code": True}
        if torch_dtype is not None:
            load_kwargs["torch_dtype"] = torch_dtype
        elif torch.cuda.is_available():
            load_kwargs["torch_dtype"] = torch.float16
        selected_device = device
        if device == "auto" and not load_in_8bit:
            if torch.cuda.is_available():
                selected_device = "cuda"
            elif torch.backends.mps.is_available():
                selected_device = "mps"
            else:
                selected_device = "cpu"

        if load_in_8bit:
            load_kwargs["load_in_8bit"] = True
            load_kwargs["device_map"] = "auto"
        elif selected_device == "cuda":
            load_kwargs["device_map"] = "auto"

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path, **load_kwargs
        )
        self.model.eval()

        if selected_device not in ("auto", "cuda") and not load_in_8bit:
            self.model = self.model.to(selected_device)

        self._device = next(self.model.parameters()).device

    # ------------------------------------------------------------------
    # CompletionService interface
    # ------------------------------------------------------------------

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        inputs = self.tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=2048
        ).to(self._device)

        gen_kwargs = {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature != 0,
            "temperature": self.temperature if self.temperature > 0 else 1.0,
            "top_p": self.top_p,
            "num_return_sequences": n_samples,
            "pad_token_id": self.tokenizer.pad_token_id,
            "output_scores": True,
            "return_dict_in_generate": True,
        }
        if self.temperature == 0:
            gen_kwargs["do_sample"] = False
            del gen_kwargs["temperature"]
            del gen_kwargs["top_p"]

        try:
            try:
                with torch.no_grad():
                    output = self.model.generate(**inputs, **gen_kwargs)
            except RuntimeError as exc:
                if gen_kwargs.get("do_sample") and "probability tensor contains" in str(exc):
                    retry_kwargs = dict(gen_kwargs)
                    retry_kwargs["do_sample"] = False
                    retry_kwargs.pop("temperature", None)
                    retry_kwargs.pop("top_p", None)
                    with torch.no_grad():
                        output = self.model.generate(**inputs, **retry_kwargs)
                else:
                    raise
        except RuntimeError as exc:
            if (
                n_samples == 1
                and gen_kwargs.get("do_sample")
                and "probability tensor contains" in str(exc)
            ):
                retry_kwargs = dict(gen_kwargs)
                retry_kwargs["do_sample"] = False
                retry_kwargs.pop("temperature", None)
                retry_kwargs.pop("top_p", None)
                with torch.no_grad():
                    output = self.model.generate(**inputs, **retry_kwargs)
            else:
                raise

        n_prompt_tokens = inputs["input_ids"].shape[1]
        results = []

        for seq_idx in range(n_samples):
            generated_ids = output.sequences[seq_idx][n_prompt_tokens:]
            generated_text = self.tokenizer.decode(
                generated_ids, skip_special_tokens=True
            )

            # Compute per-token log probabilities from scores
            log_probs = []
            if output.scores:
                for step, score in enumerate(output.scores):
                    if step >= len(generated_ids):
                        break
                    token_id = generated_ids[step].item()
                    lp = F.log_softmax(score[seq_idx], dim=-1)[token_id].item()
                    log_probs.append(lp)

            result = CompletionResult(
                text=generated_text,
                token_ids=generated_ids.tolist(),
                log_probs=log_probs,
            )

            if self.content_filter is not None:
                result = self.content_filter(result)

            results.append(result)

        return results

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ) -> list[list[CompletionResult]]:
        if not prompts:
            return []
        if n_samples != 1:
            return super().complete_many(prompts, n_samples=n_samples, batch_size=batch_size)

        grouped: list[list[CompletionResult]] = []
        for start in range(0, len(prompts), max(1, batch_size)):
            batch_prompts = prompts[start:start + max(1, batch_size)]
            inputs = self.tokenizer(
                batch_prompts,
                return_tensors="pt",
                truncation=True,
                max_length=2048,
                padding=True,
            ).to(self._device)
            gen_kwargs = {
                "max_new_tokens": self.max_new_tokens,
                "do_sample": self.temperature != 0,
                "temperature": self.temperature if self.temperature > 0 else 1.0,
                "top_p": self.top_p,
                "num_return_sequences": 1,
                "pad_token_id": self.tokenizer.pad_token_id,
                "output_scores": True,
                "return_dict_in_generate": True,
            }
            if self.temperature == 0:
                gen_kwargs["do_sample"] = False
                del gen_kwargs["temperature"]
                del gen_kwargs["top_p"]

            try:
                with torch.no_grad():
                    output = self.model.generate(**inputs, **gen_kwargs)
            except RuntimeError as exc:
                if "probability tensor contains" in str(exc):
                    retry_kwargs = dict(gen_kwargs)
                    retry_kwargs["do_sample"] = False
                    retry_kwargs.pop("temperature", None)
                    retry_kwargs.pop("top_p", None)
                    with torch.no_grad():
                        output = self.model.generate(**inputs, **retry_kwargs)
                else:
                    raise

            n_input_tokens = inputs["input_ids"].shape[1]
            for seq_idx in range(len(batch_prompts)):
                generated_ids = output.sequences[seq_idx][n_input_tokens:]
                generated_text = self.tokenizer.decode(
                    generated_ids, skip_special_tokens=True
                )
                log_probs = []
                if output.scores:
                    for step, score in enumerate(output.scores):
                        if step >= len(generated_ids):
                            break
                        token_id = generated_ids[step].item()
                        lp = F.log_softmax(score[seq_idx], dim=-1)[token_id].item()
                        log_probs.append(lp)
                result = CompletionResult(
                    text=generated_text,
                    token_ids=generated_ids.tolist(),
                    log_probs=log_probs,
                )
                if self.content_filter is not None:
                    result = self.content_filter(result)
                grouped.append([result])
        return grouped

    def log_probability(self, prompt: str, completion: str) -> float:
        return sum(self.per_token_log_probs(prompt, completion))

    def per_token_log_probs(self, prompt: str, completion: str) -> list[float]:
        """
        Teacher-forcing: compute log p(y_t | y_{<t}, prompt) for each token
        in `completion` given `prompt`.
        """
        full_text = prompt + completion
        inputs = self.tokenizer(
            full_text, return_tensors="pt", truncation=True, max_length=4096
        ).to(self._device)
        prompt_ids = self.tokenizer(
            prompt, return_tensors="pt", truncation=True
        )["input_ids"]
        n_prompt = prompt_ids.shape[1]

        with torch.no_grad():
            logits = self.model(**inputs).logits  # (1, seq_len, vocab)

        # The logit at position t predicts token t+1
        completion_logits = logits[0, n_prompt - 1: -1, :]   # shape: (n_completion, vocab)
        completion_ids = inputs["input_ids"][0, n_prompt:]     # shape: (n_completion,)

        log_probs_tensor = F.log_softmax(completion_logits, dim=-1)
        per_token = log_probs_tensor[
            range(len(completion_ids)), completion_ids
        ].tolist()
        return per_token

    def get_token_log_probs_batch(
        self,
        prompts: list[str],
        completions: list[str],
    ) -> list[list[float]]:
        """Batched version of per_token_log_probs for efficiency."""
        results = []
        for prompt, completion in zip(prompts, completions):
            results.append(self.per_token_log_probs(prompt, completion))
        return results

    @property
    def model_name(self) -> str:
        return self._model_path

    def save_pretrained(self, path: str) -> None:
        self.model.save_pretrained(path)
        self.tokenizer.save_pretrained(path)
