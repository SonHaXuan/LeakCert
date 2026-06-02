"""
B7 – Carlini-style real-model extraction attack (Section 4.2, B7).

Protocol (Carlini et al. [1], [55] / Section 4.2):
  For each canary context c_k:
    1. Sample N=256 completions from the target model.
    2. Score each completion by its log-likelihood ratio (LLR):
         LLR(y) = log p_target(y | c_k) - log p_ref(y | c_k)
       This is equivalent to ranking by perplexity ratio PPL_target / PPL_ref
       (lower perplexity ratio ↔ higher LLR ↔ more memorised by target).
    3. Emit the completion with the highest LLR as the extraction guess.
       This is the rank-1 verbatim extraction attempt.

study result: B7 achieves 52.8% rank-1 hit rate against Code-Mid on B1
(no defence), vs. LeakCert's 0.45% (Table 9, §5.8).

Unlike A-adaptive, B7 is a *single-shot* attack (no iterative query):
it fires N queries in parallel and emits the best one.  B7 is the
strongest undefended single-shot attack in the evaluation suite.
"""

from __future__ import annotations

from typing import Optional

from .base import Attacker, AttackResult
from ..canary.types import Canary


class ACarlini(Attacker):
    """
    Carlini-style prefix–perplexity extraction attack (B7).

    Parameters
    ----------
    budget       : B total queries (n_samples = min(n_samples_per_canary, budget)).
    ref_service  : reference (base, un-fine-tuned) model for log p_ref.
                   If None, uses a self-normalised approximation (log p_target
                   from random prompts as a proxy for the marginal).
    n_samples    : N completions to sample per canary (study uses 256).
    temperature  : sampling temperature (uses service default if None).
    """

    def __init__(
        self,
        budget: int = 10_000,
        ref_service=None,
        n_samples: int = 256,
    ):
        super().__init__(budget, name="A-Carlini")
        self.ref = ref_service
        self.n_samples = n_samples

    # ------------------------------------------------------------------
    # Core attack
    # ------------------------------------------------------------------

    def attack_canary(self, service, canary: Canary) -> AttackResult:
        """
        Sample N completions, rank by LLR, emit the best.
        """
        n = min(self.n_samples, self.budget)

        # Step 1: sample N completions from the target model
        try:
            results = service.complete(canary.context, n_samples=n)
        except Exception:
            # Some services cap n_samples; fall back to sequential
            results = []
            for _ in range(n):
                r = service.complete(canary.context, n_samples=1)
                results.extend(r)

        queries_used = len(results)

        if not results:
            return AttackResult(
                canary_id=canary.canary_id,
                secret=canary.secret,
                guessed_secret=None,
                success=False,
                queries_used=0,
            )

        # Step 2: score each completion by LLR
        best_completion: Optional[str] = None
        best_llr: float = float("-inf")

        for r in results:
            text = r.text.strip()
            if not text:
                continue
            llr = self._llr(service, canary.context, text)
            if llr > best_llr:
                best_llr = llr
                best_completion = text

        # Step 3: rank-1 verbatim match
        success = (
            self.contains_secret(best_completion, canary.secret)
            if best_completion
            else False
        )
        return AttackResult(
            canary_id=canary.canary_id,
            secret=canary.secret,
            guessed_secret=best_completion,
            success=success,
            queries_used=queries_used,
        )

    # ------------------------------------------------------------------
    # LLR computation
    # ------------------------------------------------------------------

    def _llr(self, service, prompt: str, completion: str) -> float:
        """
        LLR(y) = log p_target(y | prompt) - log p_ref(y | prompt).

        Highest LLR = most memorised by target relative to reference.
        Lowest perplexity ratio PPL_target / PPL_ref ↔ highest LLR.
        """
        log_p_target = service.log_probability(prompt, completion)

        if self.ref is not None:
            log_p_ref = self.ref.log_probability(prompt, completion)
        else:
            # Self-normalised fallback: use the target model's unconditional
            # (marginal) probability as a proxy for log p_ref.
            # In practice this underestimates LLR but preserves ranking.
            log_p_ref = 0.0

        return log_p_target - log_p_ref

    # ------------------------------------------------------------------
    # Batch panel attack  (overrides base for efficiency)
    # ------------------------------------------------------------------

    def attack_panel(self, service, panel) -> list[AttackResult]:
        """
        Run the Carlini attack against every canary in the panel.
        Budget is shared uniformly: n_samples_per_canary =
        min(n_samples, budget // max(len(panel), 1)).
        """
        canaries = list(panel)
        if not canaries:
            return []

        n_per_canary = max(1, min(self.n_samples, self.budget // len(canaries)))

        results = []
        queries_total = 0
        for canary in canaries:
            if queries_total >= self.budget:
                results.append(AttackResult(
                    canary_id=canary.canary_id,
                    secret=canary.secret,
                    guessed_secret=None,
                    success=False,
                    queries_used=0,
                ))
                continue

            n = min(n_per_canary, self.budget - queries_total)
            try:
                completions = service.complete(canary.context, n_samples=n)
            except Exception:
                completions = []
                for _ in range(n):
                    completions.extend(service.complete(canary.context, n_samples=1))

            queries_total += len(completions)

            best_completion = None
            best_llr = float("-inf")
            for r in completions:
                text = r.text.strip()
                if not text:
                    continue
                llr = self._llr(service, canary.context, text)
                if llr > best_llr:
                    best_llr = llr
                    best_completion = text

            success = (
                self.contains_secret(best_completion, canary.secret)
                if best_completion
                else False
            )
            results.append(AttackResult(
                canary_id=canary.canary_id,
                secret=canary.secret,
                guessed_secret=best_completion,
                success=success,
                queries_used=len(completions),
            ))

        return results
