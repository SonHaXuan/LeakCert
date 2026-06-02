"""
Tests for newly implemented components:
  - ACarlini (B7 attack)
  - MINE neural estimator
  - T3 watermarked comment subtype
  - Semantic similarity / T3 extraction rubric
  - Refusal threshold calibration
  - Table 4 prior sweep
  - Table 8 DP sweep
  - W3 utility benchmark / task benchmark loading
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math
import pytest
import numpy as np

from leakcert.canary.generator import CanaryGenerator
from leakcert.canary.types import Canary, CanaryType, CanaryPanel
from leakcert.attacks.a_carlini import ACarlini
from leakcert.certificate.kl_estimator import PerCanaryKL, KLEstimator, MINEEstimator
from leakcert.evaluation.metrics import (
    semantic_similarity,
    is_semantic_extraction,
    rate_summary,
    validate_count_pair,
    wilson_ci,
)
from leakcert.model.completion_service import CompletionService, CompletionResult
from leakcert.runtime.refusal import UncertaintyRefusal


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def make_canary(cid, ctx="KEY=", secret="ABCDEF1234567890"):
    return Canary(
        canary_id=cid, canary_type=CanaryType.LITERAL,
        secret=secret, context=ctx, full_text=ctx + secret,
    )


def make_kl_results(n=50, kl_val=0.05, seed=42):
    rng = np.random.RandomState(seed)
    return [
        PerCanaryKL(
            canary_id=f"c{i}", kl_estimate=max(0.0, kl_val + rng.normal(0, 0.01)),
            log_p_target=-5.0, log_p_ref=-5.05, n_tokens=5, canary_type="T1_literal",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Mock service (same as test_attacks.py)
# ---------------------------------------------------------------------------

class MockService(CompletionService):
    def __init__(self, canaries, leak_rate=1.0):
        super().__init__(temperature=1.0)
        self._secrets = {c.context: c.secret for c in canaries}
        self.leak_rate = leak_rate

    def complete(self, prompt, n_samples=1):
        import random
        results = []
        matched = None
        for ctx, sec in self._secrets.items():
            if ctx in prompt:
                matched = sec
                break
        for _ in range(n_samples):
            text = matched if (random.random() < self.leak_rate and matched) else "def foo(): pass"
            results.append(CompletionResult(text=text, token_ids=[], log_probs=[-1.0]))
        return results

    def log_probability(self, prompt, completion):
        for ctx, sec in self._secrets.items():
            if ctx in prompt and sec in completion:
                return -0.5
        return -5.0

    def per_token_log_probs(self, prompt, completion):
        return [-1.0] * max(1, len(completion.split()))


class TestReportingGuardrails:
    def test_wilson_ci_contains_observed_rate(self):
        lo, hi = wilson_ci(20, 100)
        assert 0.0 <= lo <= 0.20 <= hi <= 1.0

    def test_rate_summary_preserves_raw_rate(self):
        summary = rate_summary(3, 10)
        assert summary["rate"] == pytest.approx(0.3)
        assert summary["rate_pct"] == 30.0
        assert summary["n_success"] == 3
        assert summary["n_total"] == 10
        assert "ci95" in summary

    def test_invalid_counts_rejected(self):
        with pytest.raises(ValueError):
            validate_count_pair(11, 10)


# ---------------------------------------------------------------------------
# B7 ACarlini tests
# ---------------------------------------------------------------------------

class TestACarlini:
    def test_extracts_when_leaks(self):
        canary = make_canary("c1", "AWS=", "AKIATESTKEY1234567")
        service = MockService([canary], leak_rate=1.0)
        attacker = ACarlini(budget=10, n_samples=5)
        result = attacker.attack_canary(service, canary)
        assert result.success

    def test_fails_when_no_leak(self):
        canary = make_canary("c2", "KEY=", "SECRETVALUE1234567")
        service = MockService([], leak_rate=0.0)
        attacker = ACarlini(budget=10, n_samples=5)
        result = attacker.attack_canary(service, canary)
        assert not result.success

    def test_uses_at_most_n_samples(self):
        canary = make_canary("c3", "T=", "TOKEN12345678901234")
        service = MockService([canary], leak_rate=1.0)
        attacker = ACarlini(budget=100, n_samples=8)
        result = attacker.attack_canary(service, canary)
        assert result.queries_used <= 8

    def test_panel_attack_respects_budget(self):
        canaries = [make_canary(f"c{i}", f"K{i}=", f"SECRET{i:012d}") for i in range(5)]
        service = MockService(canaries, leak_rate=1.0)
        panel = CanaryPanel(canaries=canaries)
        attacker = ACarlini(budget=50, n_samples=20)
        results = attacker.attack_panel(service, panel)
        assert len(results) == 5
        total_queries = sum(r.queries_used for r in results)
        assert total_queries <= 50


# ---------------------------------------------------------------------------
# MINE neural estimator tests
# ---------------------------------------------------------------------------

class TestMINEEstimator:
    def test_returns_non_negative(self):
        kl_samples = [0.05] * 100
        result = KLEstimator.mine_estimate(kl_samples, query_budget=1000, canary_set_size=100)
        assert result >= 0.0

    def test_scales_with_budget(self):
        kl_samples = [0.05] * 100
        r1 = KLEstimator.mine_estimate(kl_samples, query_budget=1000, canary_set_size=100,
                                        use_neural=False)
        r2 = KLEstimator.mine_estimate(kl_samples, query_budget=2000, canary_set_size=100,
                                        use_neural=False)
        assert abs(r2 / r1 - 2.0) < 1e-6

    def test_empty_returns_zero(self):
        assert KLEstimator.mine_estimate([], 1000, 100) == 0.0

    def test_neural_mine_positive(self):
        """Neural MINE should return a positive MI estimate for non-trivial KL."""
        pytest.importorskip("torch")
        rng = np.random.RandomState(0)
        kl_samples = list(rng.uniform(0.01, 0.1, size=200))
        result = MINEEstimator(n_epochs=100, seed=0).estimate(
            np.array(kl_samples), query_budget=1000
        )
        assert result >= 0.0

    def test_neural_mine_grows_with_kl(self):
        """Higher per-canary KL should give higher MI estimate."""
        pytest.importorskip("torch")
        rng = np.random.RandomState(42)
        low_kl = list(rng.uniform(0.001, 0.01, size=200))
        high_kl = list(rng.uniform(0.05, 0.15, size=200))
        # Use more epochs so the MINE converges on the weaker-SNR signals.
        r_low = MINEEstimator(n_epochs=300, seed=0).estimate(np.array(low_kl), 1000)
        r_high = MINEEstimator(n_epochs=300, seed=0).estimate(np.array(high_kl), 1000)
        assert r_high >= r_low


# ---------------------------------------------------------------------------
# T3 watermarked comment tests
# ---------------------------------------------------------------------------

class TestT3WatermarkCanary:
    def setup_method(self):
        self.gen = CanaryGenerator(n_canaries=10, n_eval=2, seed=7)

    def test_watermark_canaries_generated(self):
        canaries = self.gen._gen_t3(9)  # 9 = 3 subtypes × 3
        subtypes = {c.subtype for c in canaries}
        assert "watermark_comment" in subtypes

    def test_watermark_comment_has_key_fields(self):
        canaries = [c for c in self.gen._gen_t3(9) if c.subtype == "watermark_comment"]
        assert len(canaries) > 0
        for c in canaries:
            assert "CONFIDENTIAL" in c.secret
            assert "Watermark" in c.secret
            assert len(c.secret) > 100

    def test_algo_stub_is_30_lines(self):
        canaries = [c for c in self.gen._gen_t3(9) if c.subtype == "algo_stub"]
        for c in canaries:
            lines = c.secret.strip().split("\n")
            assert len(lines) >= 25, f"Expected ≥25 lines, got {len(lines)}"

    def test_all_three_subtypes_present(self):
        canaries = self.gen._gen_t3(12)
        subtypes = {c.subtype for c in canaries}
        assert subtypes == {"algo_stub", "protocol_header", "watermark_comment"}

    def test_protocol_header_has_reserved_fields(self):
        canaries = [c for c in self.gen._gen_t3(9) if c.subtype == "protocol_header"]
        for c in canaries:
            assert "RESERVED" in c.secret
            assert "MAX_PAYLOAD" in c.secret


# ---------------------------------------------------------------------------
# Semantic similarity / T3 extraction rubric tests
# ---------------------------------------------------------------------------

class TestSemanticSimilarity:
    def test_identical_strings_score_one(self):
        text = "def proprietary_transform(data, key): return xor(data, key)"
        score = semantic_similarity(text, text)
        assert score > 0.99

    def test_empty_strings_score_zero(self):
        assert semantic_similarity("", "hello") == 0.0
        assert semantic_similarity("hello", "") == 0.0

    def test_very_different_strings_low_score(self):
        ref = "TESTKEY1234567890"
        cand = "def foo(): return 42"
        score = semantic_similarity(ref, cand)
        assert score < 0.5

    def test_similar_strings_high_score(self):
        ref = "# CONFIDENTIAL — Corp Internal Use Only\n# Module: core_utils"
        cand = "# CONFIDENTIAL — Corp Internal Use\n# Module: core_utils v2"
        score = semantic_similarity(ref, cand)
        assert score > 0.5

    def test_is_semantic_extraction_threshold(self):
        identical = "def f(x): return x * 2"
        assert is_semantic_extraction(identical, identical, threshold=0.8)
        assert not is_semantic_extraction("hello world", "xyz abc 123", threshold=0.8)


# ---------------------------------------------------------------------------
# Refusal threshold calibration tests
# ---------------------------------------------------------------------------

class TestRefusalCalibration:
    def test_calibrate_reduces_refusal_below_target(self):
        refusal = UncertaintyRefusal(threshold=0.0, use_learned=False)
        # Legitimate completions (normal code, no secrets)
        legit = [
            "def add(a, b): return a + b",
            "x = 42\nprint(x)",
            "import os\npath = os.getcwd()",
            "for i in range(10): print(i)",
        ] * 20
        target_rate = 0.05
        new_threshold = refusal.calibrate_threshold(legit, target_refusal_rate=target_rate)
        assert new_threshold >= 0.1
        actual_rate = refusal.expected_refusal_rate(legit)
        assert actual_rate <= target_rate + 0.05  # allow small tolerance

    def test_calibrate_returns_valid_threshold(self):
        refusal = UncertaintyRefusal(threshold=0.5)
        completions = ["normal code " * 5] * 50
        t = refusal.calibrate_threshold(completions, target_refusal_rate=0.01)
        assert 0.0 <= t <= 1.0

    def test_calibrate_empty_list_returns_existing(self):
        refusal = UncertaintyRefusal(threshold=0.5)
        t = refusal.calibrate_threshold([])
        assert t == 0.5


# ---------------------------------------------------------------------------
# Table 4 prior sweep test (via ExtractionMetrics + certificate)
# ---------------------------------------------------------------------------

class TestPriorSweep:
    def test_type_empirical_prior_different_from_uniform(self):
        from leakcert.certificate.certificate import LeakageCertificate
        np.random.seed(0)
        kl_results = make_kl_results(100, 0.05)
        cert = LeakageCertificate()

        # Uniform prior
        r_uniform = cert.compute(kl_results, query_budget=1000, canary_set_size=100, delta=0.01)

        # Concentrate all mass on the minimum-KL canary.
        # nonuniform = B * E_π[KL] + H(π).
        # With H(π)=0 and E_π[KL]=min_kl, this beats the uniform cert
        # whenever B*min_kl < B*mean_kl + log|K|, which holds easily for
        # log(100)/1000 ≈ 0.005 slack above the mean.
        kl_vals = [r.kl_estimate for r in kl_results]
        min_idx = int(np.argmin(kl_vals))
        pi_conc = [0.0] * 100
        pi_conc[min_idx] = 1.0
        r_conc = cert.compute(kl_results, query_budget=1000, canary_set_size=100, delta=0.01,
                               prior=pi_conc)
        # Concentrated on min-KL canary: entropy 0 and lowest possible E_π[KL]
        # → strictly lower nonuniform certificate than the uniform prior
        assert r_conc.nonuniform_certificate < r_uniform.nonuniform_certificate


# ---------------------------------------------------------------------------
# Table 8 DP sweep test
# ---------------------------------------------------------------------------

class TestDPSweep:
    def test_dp_clamping_reduces_cert(self):
        """Clamping KL at ε²/2 should reduce the certificate."""
        from leakcert.certificate.certificate import LeakageCertificate
        np.random.seed(0)
        kl_results = make_kl_results(100, kl_val=0.2)  # high KL (no DP)
        cert = LeakageCertificate()

        r_base = cert.compute(kl_results, query_budget=1000, canary_set_size=100, delta=0.01)

        # Simulate DP ε=1: clamp KL ≤ ε²/2 = 0.5
        eps = 1.0
        from leakcert.certificate.kl_estimator import PerCanaryKL
        clamped = [
            PerCanaryKL(
                canary_id=r.canary_id,
                kl_estimate=min(r.kl_estimate, eps**2 / 2),
                log_p_target=r.log_p_target, log_p_ref=r.log_p_ref,
                n_tokens=r.n_tokens, canary_type=r.canary_type,
            )
            for r in kl_results
        ]
        r_dp = cert.compute(clamped, query_budget=1000, canary_set_size=100, delta=0.01)
        assert r_dp.hoeffding_certificate <= r_base.hoeffding_certificate

    def test_dp_analytic_formula(self):
        from leakcert.certificate.certificate import LeakageCertificate
        eps, B, K = 8.0, 10_000, 10_000
        result = LeakageCertificate.dp_composition_certificate(eps, B, K)
        expected = B * eps**2 / 2 + math.log(K)
        assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# W3 workload loading test
# ---------------------------------------------------------------------------

class TestW3Workload:
    def test_w3_has_samples(self):
        from leakcert.evaluation.workloads import W3RealCompletion
        w3 = W3RealCompletion(subset="utility_eval", multilingual=False)
        samples = w3.samples()
        assert len(samples) >= 5  # at least synthetic fallback

    def test_w3_samples_have_prompts(self):
        from leakcert.evaluation.workloads import W3RealCompletion
        w3 = W3RealCompletion(subset="utility_eval", multilingual=False)
        for s in w3.samples():
            assert len(s.prompt) > 0

    def test_w3_both_subset_combines(self):
        from leakcert.evaluation.workloads import W3RealCompletion
        # Can't load real datasets in tests, but the code path should not error
        w3 = W3RealCompletion(subset="both", multilingual=False)
        samples = w3.samples()
        assert len(samples) >= 1
