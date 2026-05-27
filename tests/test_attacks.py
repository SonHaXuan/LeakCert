"""Unit tests for attacker modules (mock service)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from leakcert.attacks.a_fixed import AFixed
from leakcert.attacks.a_grid import AGrid
from leakcert.attacks.a_adaptive import AAdaptive
from leakcert.attacks.a_greedy_lrt import AGreedyLRT
from leakcert.canary.types import Canary, CanaryType, CanaryPanel
from leakcert.model.completion_service import CompletionService, CompletionResult


class MockService(CompletionService):
    """Mock that always returns the canary secret when queried with its context."""

    def __init__(self, canaries: list[Canary], leak_rate: float = 1.0):
        super().__init__(temperature=1.0)
        self._secrets = {c.context: c.secret for c in canaries}
        self.leak_rate = leak_rate
        self.query_count = 0

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        import random
        self.query_count += n_samples
        results = []
        # Match if prompt contains any registered context (handles paraphrase prompts)
        matched_secret = None
        for ctx, sec in self._secrets.items():
            if ctx in prompt:
                matched_secret = sec
                break
        for _ in range(n_samples):
            if random.random() < self.leak_rate and matched_secret is not None:
                text = matched_secret
            else:
                text = "def foo(): return 42"
            results.append(CompletionResult(text=text, token_ids=[], log_probs=[-1.0]))
        return results

    def log_probability(self, prompt: str, completion: str) -> float:
        if prompt in self._secrets and self._secrets[prompt] in completion:
            return -0.5   # high probability for the canary
        return -5.0       # low probability otherwise

    def per_token_log_probs(self, prompt: str, completion: str) -> list[float]:
        return [-1.0] * len(completion.split())


def make_canary(cid: str, ctx: str = "KEY=", secret: str = "ABCD1234") -> Canary:
    return Canary(
        canary_id=cid,
        canary_type=CanaryType.LITERAL,
        secret=secret,
        context=ctx,
        full_text=ctx + secret,
    )


class TestAFixed:
    def test_extracts_when_model_leaks(self):
        canary = make_canary("c1", "AWS_SECRET=", "AKIATESTKEY12345678")
        service = MockService([canary], leak_rate=1.0)
        attacker = AFixed(budget=5)
        result = attacker.attack_canary(service, canary)
        assert result.success

    def test_fails_when_model_does_not_leak(self):
        canary = make_canary("c2", "SECRET=", "MYSECRETVALUE12345")
        service = MockService([], leak_rate=0.0)   # never leaks
        attacker = AFixed(budget=5)
        result = attacker.attack_canary(service, canary)
        assert not result.success

    def test_respects_budget(self):
        canary = make_canary("c3", "KEY=", "SOMEKEY")
        service = MockService([], leak_rate=0.0)
        attacker = AFixed(budget=3)
        result = attacker.attack_canary(service, canary)
        assert result.queries_used <= 3

    def test_panel_extraction_rate(self):
        canaries = [make_canary(f"c{i}", f"KEY{i}=", f"SECRET{i}") for i in range(10)]
        service = MockService(canaries, leak_rate=1.0)
        panel = CanaryPanel(canaries=canaries)
        attacker = AFixed(budget=5)
        results = attacker.attack_panel(service, panel)
        rate = attacker.extraction_success_rate(results)
        assert rate == 1.0   # all canaries extracted


class TestAAdaptive:
    def test_tries_multiple_paraphrase_modes(self):
        canary = make_canary("c1", "AWS=", "AKIATEST")
        service = MockService([canary], leak_rate=0.0)
        attacker = AAdaptive(budget=50, n_per_mode=2)
        result = attacker.attack_canary(service, canary)
        # 5 modes × 2 queries = 10 queries (but budget caps it)
        assert result.queries_used <= 50

    def test_succeeds_when_leaks(self):
        canary = make_canary("c2", "TOKEN=", "JWTBODYVALUE12345")
        service = MockService([canary], leak_rate=1.0)
        attacker = AAdaptive(budget=20)
        result = attacker.attack_canary(service, canary)
        assert result.success


class TestAGreedyLRT:
    def test_positive_llr_leads_to_extraction(self):
        """When target log-prob >> ref log-prob, SPRT should decide H_1."""
        canary = make_canary("c1", "K=", "SECRET99")
        service = MockService([canary], leak_rate=1.0)

        class HighLRTRef(MockService):
            def log_probability(self, prompt, completion):
                return -10.0   # very low ref prob → high LLR

        ref = HighLRTRef([], leak_rate=0.0)
        attacker = AGreedyLRT(budget=100, ref_service=ref, alpha=0.05, beta=0.05)
        result = attacker.attack_canary(service, canary)
        assert result.queries_used <= 100

    def test_expected_queries_formula(self):
        """Wald's identity should give a finite positive number."""
        n = AGreedyLRT.expected_queries_to_decision(0.05, alpha=0.05, beta=0.05)
        assert 0 < n < float("inf")

    def test_zero_kl_means_infinite_queries(self):
        n = AGreedyLRT.expected_queries_to_decision(0.0, alpha=0.05, beta=0.05)
        assert n == float("inf")


class TestVerbatimMatch:
    def test_exact_match(self):
        from leakcert.attacks.base import Attacker
        assert Attacker.verbatim_match("ABCD", "ABCD")
        assert not Attacker.verbatim_match("ABCD", "ABCE")

    def test_contains_secret(self):
        from leakcert.attacks.base import Attacker
        assert Attacker.contains_secret("the key is ABCD1234 here", "ABCD1234")
        assert not Attacker.contains_secret("nothing here", "ABCD1234")

    def test_whitespace_normalised(self):
        from leakcert.attacks.base import Attacker
        assert Attacker.verbatim_match("  ABCD  ", "ABCD")
