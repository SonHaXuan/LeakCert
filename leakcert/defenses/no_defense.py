"""B1 – No defence: greedy decoding at τ=1.0, top-p=1.0, no filter."""

from ..model.completion_service import CompletionResult
from .base import DefenseWrapper, DefenseConfig


class NoDefense(DefenseWrapper):
    """
    B1: No defence baseline.
    Passes all queries directly to the base service unchanged.
    """

    def __init__(self, base_service):
        super().__init__(base_service, DefenseConfig(name="B1_no_defense"))

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        return self.base.complete(prompt, n_samples)
