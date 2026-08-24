"""
B2 – Temperature sampling defence.

study (Section 4.2, B2):
  τ ∈ {0.2, 0.5, 1.5}; headline number reported at τ=0.5.

Lower temperature sharpens the distribution (more greedy), reducing
the variance of memorised outputs.  Higher temperature flattens it.
"""

from __future__ import annotations

from ..model.completion_service import CompletionResult
from .base import DefenseConfig, DefenseWrapper


class TemperatureDefense(DefenseWrapper):
    """
    B2: Temperature-sampling defence.

    Overrides the base service temperature at completion time.
    """

    def __init__(self, base_service, temperature: float = 0.5):
        config = DefenseConfig(
            name=f"B2_temperature_{temperature}",
            description=f"Temperature sampling τ={temperature}",
        )
        super().__init__(base_service, config)
        self._override_temperature = temperature

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        old_temp = self.base.temperature
        self.base.temperature = self._override_temperature
        try:
            results = self.base.complete(prompt, n_samples)
        finally:
            self.base.temperature = old_temp
        return results

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ) -> list[list[CompletionResult]]:
        old_temp = self.base.temperature
        self.base.temperature = self._override_temperature
        try:
            results = self.base.complete_many(
                prompts, n_samples=n_samples, batch_size=batch_size
            )
        finally:
            self.base.temperature = old_temp
        return results
