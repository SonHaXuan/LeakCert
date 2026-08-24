"""
A-fixed attacker: uses a fixed prompt template, issuing B identical queries
and checking whether the secret appears in any response.

This is the simplest attack and serves as the lower-bound adversary.
Corresponds to B7 (Carlini-style) when using N=256 samples with perplexity
ranking.
"""

from __future__ import annotations

from ..canary.types import Canary
from .base import Attacker, AttackResult


class AFixed(Attacker):
    """
    Fixed-template attacker.

    Queries the service B times with the canary's natural context c_k.
    Reports success if any response contains k verbatim.

    Parameters
    ----------
    n_samples : number of completions per canary (up to budget B).
    use_rank  : if True, rank completions by log-perplexity and emit rank-1
                (Carlini-style, B7).  Requires `ref_service` to be set.
    """

    def __init__(
        self,
        budget: int = 10_000,
        n_samples: int = 1,
        use_rank: bool = False,
        ref_service=None,
    ):
        super().__init__(budget, name="A-fixed")
        self.n_samples = min(n_samples, budget)
        self.use_rank = use_rank
        self.ref_service = ref_service

    def attack_canary(self, service, canary: Canary) -> AttackResult:
        queries_used = 0
        query_history = []
        response_history = []

        if self.use_rank and self.ref_service is not None:
            # Carlini-style B7: rank N completions by perplexity ratio
            best_completion, queries_used = self._carlini_attack(service, canary)
            success = self.contains_secret(best_completion, canary.secret)
            return AttackResult(
                canary_id=canary.canary_id,
                secret=canary.secret,
                guessed_secret=best_completion,
                success=success,
                queries_used=queries_used,
            )

        # Simple: query B times, success if any hit
        for _ in range(self.n_samples):
            if queries_used >= self.budget:
                break
            results = service.complete(canary.context, n_samples=1)
            queries_used += 1
            for r in results:
                query_history.append(canary.context)
                response_history.append(r.text)
                if self.contains_secret(r.text, canary.secret):
                    return AttackResult(
                        canary_id=canary.canary_id,
                        secret=canary.secret,
                        guessed_secret=r.text,
                        success=True,
                        queries_used=queries_used,
                        query_history=query_history,
                        response_history=response_history,
                    )

        return AttackResult(
            canary_id=canary.canary_id,
            secret=canary.secret,
            guessed_secret=None,
            success=False,
            queries_used=queries_used,
            query_history=query_history,
            response_history=response_history,
        )

    def _carlini_attack(self, service, canary: Canary) -> tuple[str, int]:
        """
        Carlini-style attack (B7): generate N completions, rank by
        perplexity ratio p_target(y|c) / p_ref(y|c), emit rank-1.
        """
        n = min(self.n_samples, 256)  # study uses N=256
        completions = service.complete(canary.context, n_samples=n)
        if not completions:
            return "", n

        if self.ref_service is None:
            # No reference model: just return the first completion
            return completions[0].text, n

        # Rank by log-likelihood ratio
        scored = []
        for comp in completions:
            if not comp.text.strip():
                continue
            log_p_target = sum(comp.log_probs) if comp.log_probs else 0.0
            log_p_ref = self.ref_service.log_probability(canary.context, comp.text)
            score = log_p_target - log_p_ref
            scored.append((score, comp.text))

        if not scored:
            return completions[0].text, n

        scored.sort(key=lambda x: -x[0])
        return scored[0][1], n
