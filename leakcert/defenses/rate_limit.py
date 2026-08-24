"""
B4 – Rate limit only: 1,000 queries per API key per day, no other defence.

study (Section 4.2, B4):
  Hard cap of 1,000 queries/API-key/day with no content filter or DP.
  Demonstrates that rate limiting alone keeps the certificate meaningful
  (removes the vacuous regime) but does not reduce per-query leakage.

Key insight (Section 5.10): the certificate becomes vacuous at B → ∞.
Rate limiting prevents this — it is a definitional component of any
non-trivial certificate, not a privacy defence in the traditional sense.
"""

from __future__ import annotations

from ..model.completion_service import CompletionResult
from ..runtime.rate_limiter import RateLimiter
from .base import DefenseConfig, DefenseWrapper

REFUSAL_TOKEN = "<|RATE_LIMITED|>"


class RateLimitDefense(DefenseWrapper):
    """
    B4: Rate-limit-only defence.

    Enforces a per-API-key daily query cap but applies no other
    decoding or output transformation.
    """

    def __init__(self, base_service, queries_per_day: int = 1_000):
        config = DefenseConfig(
            name=f"B4_rate_limit_{queries_per_day}",
            description=f"Rate limit: {queries_per_day} queries/API-key/day",
        )
        super().__init__(base_service, config)
        self._limiter = RateLimiter(
            query_budget=queries_per_day,
            window_seconds=24 * 3600,
        )
        self._default_key = "default"

    def complete(
        self, prompt: str, n_samples: int = 1, api_key: str = "default"
    ) -> list[CompletionResult]:
        allowed, reason = self._limiter.check(api_key)
        if not allowed:
            return [
                CompletionResult(
                    text=REFUSAL_TOKEN,
                    token_ids=[],
                    log_probs=[],
                    was_refused=True,
                    refusal_reason=reason,
                )
            ] * n_samples
        self._limiter.record_query(api_key)
        return self.base.complete(prompt, n_samples)
