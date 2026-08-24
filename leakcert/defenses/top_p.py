"""
B3 – Top-p (nucleus) sampling defence.

study (Section 4.2, B3):
  p ∈ {0.5, 0.7, 0.9}; headline number at p=0.7.

Top-p truncates the distribution to the smallest set of tokens with
cumulative probability ≥ p, preventing low-probability memorised tokens.
"""

from __future__ import annotations

from ..model.completion_service import CompletionResult
from .base import DefenseConfig, DefenseWrapper


class TopPDefense(DefenseWrapper):
    """
    B3: Top-p nucleus sampling defence.
    """

    def __init__(self, base_service, top_p: float = 0.7):
        config = DefenseConfig(
            name=f"B3_top_p_{top_p}",
            description=f"Top-p nucleus sampling p={top_p}",
        )
        super().__init__(base_service, config)
        self._override_top_p = top_p

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        old_top_p = self.base.top_p
        self.base.top_p = self._override_top_p
        try:
            results = self.base.complete(prompt, n_samples)
        finally:
            self.base.top_p = old_top_p
        return results

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ) -> list[list[CompletionResult]]:
        old_top_p = self.base.top_p
        self.base.top_p = self._override_top_p
        try:
            results = self.base.complete_many(
                prompts, n_samples=n_samples, batch_size=batch_size
            )
        finally:
            self.base.top_p = old_top_p
        return results
