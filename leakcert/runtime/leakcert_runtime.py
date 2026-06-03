"""
LeakCert Runtime — the online release monitor (Section 3.7, Figure 1).

Composes four components in sequence for every incoming query:
  1. Certificate Generator  : rolling KL estimate; throttle if budget exceeded
  2. Rate Limiter           : per-API-key hard query cap
  3. Uncertainty Refusal    : classifier φ_u replaces high-score outputs with ⊥
  4. Target-String Suppression: regex + hash zeroes known secret patterns

The certificate path determines whether the runtime emits, rate-limits, or
refuses the next response.  Figure 1 of the study.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..model.completion_service import CompletionService
from .rate_limiter import RateLimiter
from .refusal import UncertaintyRefusal
from .suppression import TargetStringSuppression

logger = logging.getLogger(__name__)

REFUSAL_TEXT = "<|LEAKCERT_REFUSAL|>"


@dataclass
class RuntimeConfig:
    """Configuration for the LeakCert runtime."""

    # Certificate budget
    query_budget: int = 10_000         # B per API key per window
    kl_budget: Optional[float] = None  # cumulative KL threshold (auto from cert if None)

    # Rate limiting
    window_seconds: float = 10 * 24 * 3600   # 10-day rolling window

    # Uncertainty refusal
    refusal_threshold: float = 0.5
    use_learned_refusal: bool = True
    use_refusal_heuristics: bool = True
    target_refusal_rate: float = 0.01   # 1% as in study
    refusal_model_path: Optional[str] = None

    # Target suppression
    use_suppression: bool = True
    use_canary_hashes: bool = False   # register canaries for hash-based suppression

    # E6 component ablation flags
    # Setting any to False removes that component from the runtime pipeline.
    use_accounting: bool = True   # C1: KL certificate budget tracking
    use_rate_limit: bool = True   # C2: per-API-key rate limiter
    use_refusal: bool = True      # C3: uncertainty-aware refusal classifier

    # Logging
    audit_log_path: Optional[str] = None


@dataclass
class RuntimeDecision:
    """Decision record for a single query."""
    api_key: str
    prompt: str
    outcome: str   # "emit" | "throttled" | "refused" | "suppressed"
    completion: Optional[str]
    latency_ms: float
    kl_contribution: float = 0.0
    queries_used: int = 0
    refusal_score: float = 0.0
    timestamp: float = field(default_factory=time.time)


class LeakCertRuntime:
    """
    Online release monitor for a code-completion service.

    Usage
    -----
    runtime = LeakCertRuntime(
        service=fine_tuned_service,
        kl_estimator=estimator,
        config=RuntimeConfig(query_budget=10_000),
    )
    result = runtime.handle_query(api_key="user123", prompt="AWS_SECRET_ACCESS_KEY = \\\"")
    """

    def __init__(
        self,
        service: CompletionService,
        kl_estimator=None,
        config: Optional[RuntimeConfig] = None,
        panel=None,    # CanaryPanel for hash registration
    ):
        self.service = service
        self.kl_estimator = kl_estimator
        self.config = config or RuntimeConfig()
        cfg = self.config

        # Component 2: Rate Limiter
        self.rate_limiter = RateLimiter(
            query_budget=cfg.query_budget,
            window_seconds=cfg.window_seconds,
            kl_budget=cfg.kl_budget,
        )

        # Component 3: Uncertainty Refusal
        self.refusal = UncertaintyRefusal(
            threshold=cfg.refusal_threshold,
            use_learned=cfg.use_learned_refusal,
            use_heuristics=cfg.use_refusal_heuristics,
        )
        if cfg.refusal_model_path:
            try:
                self.refusal.load(cfg.refusal_model_path)
                self.refusal.threshold = cfg.refusal_threshold
                logger.info("Loaded refusal model from %s", cfg.refusal_model_path)
            except Exception as e:
                logger.warning("Failed to load refusal model from %s: %s", cfg.refusal_model_path, e)

        # Component 4: Target-String Suppression
        self.suppression = TargetStringSuppression(
            use_canary_hashes=cfg.use_canary_hashes,
        )
        if panel is not None and cfg.use_canary_hashes:
            self.suppression.register_panel(panel)

        # Component 1: Certificate Generator — rolling KL accumulator
        self._rolling_kl: dict[str, float] = {}  # api_key → cumulative KL
        self._audit_log: list[RuntimeDecision] = []

    # ------------------------------------------------------------------
    # Core query handler
    # ------------------------------------------------------------------

    def handle_query(self, api_key: str, prompt: str) -> RuntimeDecision:
        """
        Process a single completion query through all four runtime components.
        Returns a RuntimeDecision with the outcome and final completion text.
        """
        t0 = time.time()

        # ── Component 2: Rate Limiter (C2) ────────────────────────────
        if self.config.use_rate_limit:
            allowed, reason = self.rate_limiter.check(api_key)
            if not allowed:
                decision = RuntimeDecision(
                    api_key=api_key,
                    prompt=prompt,
                    outcome="throttled",
                    completion=REFUSAL_TEXT,
                    latency_ms=(time.time() - t0) * 1000,
                    queries_used=self.rate_limiter.get_state(api_key).query_count,
                )
                self._log(decision)
                return decision

        # ── Generate completion ────────────────────────────────────────
        result = self.service.complete_one(prompt)
        completion_text = result.text

        # ── Component 1: Certificate Generator / KL accounting (C1) ──
        kl_contrib = 0.0
        if self.config.use_accounting and self.kl_estimator is not None:
            try:
                kl_contrib = self.kl_estimator.streaming_kl_contribution(
                    prompt, completion_text
                )
            except Exception as e:
                logger.debug(f"KL estimation error: {e}")

        # Record query against rate limiter (updates KL budget)
        if self.config.use_rate_limit:
            self.rate_limiter.record_query(api_key, kl_contrib)

        # ── Component 3: Uncertainty-Aware Refusal (C3) ───────────────
        refusal_decision_score = 0.0
        if self.config.use_refusal:
            refusal_decision = self.refusal.decide(completion_text)
            refusal_decision_score = refusal_decision.score
            if refusal_decision.should_refuse:
                decision = RuntimeDecision(
                    api_key=api_key,
                    prompt=prompt,
                    outcome="refused",
                    completion=REFUSAL_TEXT,
                    latency_ms=(time.time() - t0) * 1000,
                    kl_contribution=kl_contrib,
                    queries_used=self.rate_limiter.get_state(api_key).query_count
                    if self.config.use_rate_limit else 0,
                    refusal_score=refusal_decision.score,
                )
                self._log(decision)
                return decision

        # ── Component 4: Target-String Suppression (C4) ───────────────
        if self.config.use_suppression:
            supp = self.suppression.filter(completion_text)
            if supp.was_suppressed:
                completion_text = supp.suppressed_text
                decision = RuntimeDecision(
                    api_key=api_key,
                    prompt=prompt,
                    outcome="suppressed",
                    completion=completion_text,
                    latency_ms=(time.time() - t0) * 1000,
                    kl_contribution=kl_contrib,
                    queries_used=self.rate_limiter.get_state(api_key).query_count
                    if self.config.use_rate_limit else 0,
                    refusal_score=refusal_decision_score,
                )
                self._log(decision)
                return decision

        # ── Emit ──────────────────────────────────────────────────────
        decision = RuntimeDecision(
            api_key=api_key,
            prompt=prompt,
            outcome="emit",
            completion=completion_text,
            latency_ms=(time.time() - t0) * 1000,
            kl_contribution=kl_contrib,
            queries_used=self.rate_limiter.get_state(api_key).query_count
            if self.config.use_rate_limit else 0,
            refusal_score=refusal_decision_score,
        )
        self._log(decision)
        return decision

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    def _log(self, decision: RuntimeDecision) -> None:
        self._audit_log.append(decision)
        if self.config.audit_log_path:
            import json
            with open(self.config.audit_log_path, "a") as f:
                f.write(json.dumps({
                    "api_key": decision.api_key,
                    "outcome": decision.outcome,
                    "kl": decision.kl_contribution,
                    "latency_ms": decision.latency_ms,
                    "ts": decision.timestamp,
                }) + "\n")

    def get_audit_log(self) -> list[RuntimeDecision]:
        return list(self._audit_log)

    def refusal_rate(self) -> float:
        """Fraction of queries that resulted in refusal or throttling."""
        if not self._audit_log:
            return 0.0
        refused = sum(
            1 for d in self._audit_log if d.outcome in ("refused", "throttled")
        )
        return refused / len(self._audit_log)

    def latency_stats(self) -> dict:
        """Median and p99 per-query latency overhead in ms."""
        import numpy as np
        latencies = [d.latency_ms for d in self._audit_log]
        if not latencies:
            return {"median": 0.0, "p99": 0.0}
        return {
            "median": float(np.median(latencies)),
            "p99": float(np.percentile(latencies, 99)),
        }
