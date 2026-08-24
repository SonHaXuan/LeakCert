"""
Rate limiter: enforces a per-API-key query budget consistent with the
published certificate (Section 3.7, Figure 1).

Without rate limiting the certificate bound is vacuous for B → ∞
(Section 5.10).  The rate limiter is therefore a definitional component,
not an optional optimisation.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class APIKeyState:
    """State for a single API key."""

    query_count: int = 0
    cumulative_kl: float = 0.0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    throttled: bool = False


class RateLimiter:
    """
    Per-API-key rate limiter.

    Enforces:
      1. Hard query cap:  once an API key has issued B_max queries it is throttled.
      2. Rolling window:  optionally resets counts after window_seconds.
      3. KL budget:       throttle if cumulative KL exceeds the certificate budget.

    Parameters
    ----------
    query_budget    : B_max per API key (study: 10^4 per 10-day window)
    window_seconds  : rolling window for budget reset (default: 10 days)
    kl_budget       : KL budget threshold (certificate value); None = no KL throttle
    """

    def __init__(
        self,
        query_budget: int = 10_000,
        window_seconds: float = 10 * 24 * 3600,  # 10 days
        kl_budget: float | None = None,
    ):
        self.query_budget = query_budget
        self.window_seconds = window_seconds
        self.kl_budget = kl_budget
        self._states: dict[str, APIKeyState] = defaultdict(APIKeyState)
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def check(self, api_key: str) -> tuple[bool, str]:
        """
        Check whether an API key is allowed to issue another query.

        Returns (allowed: bool, reason: str).
        """
        with self._lock:
            state = self._states[api_key]
            now = time.time()

            # Rolling window reset
            if now - state.first_seen > self.window_seconds:
                state.query_count = 0
                state.cumulative_kl = 0.0
                state.first_seen = now
                state.throttled = False

            if state.query_count >= self.query_budget:
                state.throttled = True
                return False, f"query_budget_exceeded (B={self.query_budget})"

            if self.kl_budget is not None and state.cumulative_kl >= self.kl_budget:
                state.throttled = True
                return False, f"kl_budget_exceeded ({state.cumulative_kl:.2f} nats)"

        return True, "allowed"

    def record_query(self, api_key: str, kl_contribution: float = 0.0) -> None:
        """Record that a query was issued and update cumulative KL."""
        with self._lock:
            state = self._states[api_key]
            state.query_count += 1
            state.cumulative_kl += kl_contribution
            state.last_seen = time.time()

    def get_state(self, api_key: str) -> APIKeyState:
        with self._lock:
            return self._states[api_key]

    def remaining_budget(self, api_key: str) -> int:
        state = self.get_state(api_key)
        return max(0, self.query_budget - state.query_count)

    def reset(self, api_key: str) -> None:
        with self._lock:
            self._states[api_key] = APIKeyState()

    def all_states(self) -> dict[str, APIKeyState]:
        with self._lock:
            return dict(self._states)
