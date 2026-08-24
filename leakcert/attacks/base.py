"""
Abstract attacker base class.

Definition 3 (study §3.2): An attacker A with budget B ∈ ℕ is a sequence of
(possibly history-dependent) prompts x_1, x_2, …, x_B where
x_t = f_t(y_{1:t-1}) for some measurable f_t.

The attacker's observation after t queries is Y^t = (y_1, …, y_t) with
y_i ~ M_θ(·|x_i).  The attacker's guess at the canary set is K̂ = g(Y^B).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AttackResult:
    """Result of a single attack run against one canary."""

    canary_id: str
    secret: str
    guessed_secret: str | None
    success: bool  # guessed_secret == secret (verbatim)
    semantic_success: bool = False  # model judge for T3 canaries
    queries_used: int = 0
    query_history: list[str] = field(default_factory=list)
    response_history: list[str] = field(default_factory=list)


class Attacker(ABC):
    """
    Abstract adaptive black-box attacker with budget B.

    Parameters
    ----------
    budget      : B — maximum number of queries to the service.
    name        : human-readable attacker name (for tables).
    """

    def __init__(self, budget: int = 10_000, name: str = "attacker"):
        self.budget = budget
        self.name = name

    @abstractmethod
    def attack_canary(self, service, canary) -> AttackResult:
        """
        Run a budget-B attack against a single canary.
        Returns an AttackResult with the guess and success flag.
        """

    def attack_panel(self, service, panel) -> list[AttackResult]:
        """Run the attack against every canary in a panel."""
        results = []
        for canary in panel:
            result = self.attack_canary(service, canary)
            results.append(result)
        return results

    def extraction_success_rate(self, results: list[AttackResult]) -> float:
        """Fraction of canaries successfully extracted (verbatim)."""
        if not results:
            return 0.0
        return sum(r.success for r in results) / len(results)

    @staticmethod
    def verbatim_match(guess: str, secret: str) -> bool:
        """Strict verbatim match (normalised whitespace)."""
        return guess.strip() == secret.strip()

    @staticmethod
    def contains_secret(text: str, secret: str) -> bool:
        """Check if `text` contains `secret` as a substring."""
        return secret.strip() in text
