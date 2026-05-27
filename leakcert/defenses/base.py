"""
Abstract defense wrapper.

All defenses wrap a base CompletionService and intercept the complete() call
to apply a decoding-time or output-time transformation.  This matches the
study's Definition 1 (M_θ with parameters τ, top-p, φ) and the discussion
in Theorem 15 (utility-leakage lower bound).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..model.completion_service import CompletionService, CompletionResult


@dataclass
class DefenseConfig:
    name: str = "defense"
    description: str = ""


class DefenseWrapper(CompletionService, ABC):
    """
    Wraps a base CompletionService with a defense transformation.
    """

    def __init__(self, base_service: CompletionService, config: DefenseConfig):
        super().__init__(
            temperature=base_service.temperature,
            top_p=base_service.top_p,
            max_new_tokens=base_service.max_new_tokens,
        )
        self.base = base_service
        self.config = config

    def log_probability(self, prompt: str, completion: str) -> float:
        return self.base.log_probability(prompt, completion)

    def per_token_log_probs(self, prompt: str, completion: str) -> list[float]:
        return self.base.per_token_log_probs(prompt, completion)

    @property
    def model_name(self) -> str:
        return f"{self.config.name}({self.base.model_name})"
