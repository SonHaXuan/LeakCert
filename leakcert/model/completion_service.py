"""
Abstract base class for code-completion services.

Definition 1 (study §3.2): A code-completion service is a randomised mapping
M : X → Δ(Y) from prompt space X to distributions over output space Y.
Parameterised by sampling temperature τ, top-p cutoff, and optional content
filter φ : Y → Y ∪ {⊥}.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CompletionResult:
    """Output of a single completion query."""
    text: str                       # generated text y ~ M_θ(·|x)
    token_ids: list[int]
    log_probs: list[float]          # per-token log probabilities log p(y_t | y_{<t}, x)
    was_refused: bool = False       # True if the runtime replaced y with ⊥
    refusal_reason: Optional[str] = None


class CompletionService(ABC):
    """
    Abstract completion service M_θ : X → Δ(Y).

    Subclasses must implement `complete` and `log_probability`.
    The `temperature`, `top_p`, and `content_filter` attributes
    control the decoding-time parameters (baselines B2, B3, B5).
    """

    def __init__(
        self,
        temperature: float = 1.0,
        top_p: float = 1.0,
        max_new_tokens: int = 128,
        content_filter=None,
    ):
        self.temperature = temperature
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens
        self.content_filter = content_filter

    @abstractmethod
    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        """
        Sample n_samples completions from M_θ(·|prompt).
        Returns n_samples CompletionResult objects.
        """

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ) -> list[list[CompletionResult]]:
        """Batch-friendly completion API with a sequential fallback."""
        return [self.complete(prompt, n_samples=n_samples) for prompt in prompts]

    @abstractmethod
    def log_probability(self, prompt: str, completion: str) -> float:
        """
        Compute log p_θ(completion | prompt) — sum of per-token log probs.
        Required for certificate KL estimation and LRT attacker.
        """

    @abstractmethod
    def per_token_log_probs(self, prompt: str, completion: str) -> list[float]:
        """
        Per-token log p_θ(y_t | y_{<t}, prompt).
        Used in the LRT attacker and KL estimator.
        """

    def complete_one(self, prompt: str) -> CompletionResult:
        """Convenience wrapper: single sample."""
        results = self.complete(prompt, n_samples=1)
        return results[0]

    @property
    def model_name(self) -> str:
        return self.__class__.__name__
