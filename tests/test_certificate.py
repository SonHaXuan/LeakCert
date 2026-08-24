"""
Unit tests for the certificate module.

Verifies Theorems 5, 7, 10, 13, 17 against known analytical values.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from leakcert.certificate.certificate import CertificateResult, LeakageCertificate
from leakcert.certificate.kl_estimator import PerCanaryKL


def make_kl_results(n: int, kl_val: float = 0.05) -> list[PerCanaryKL]:
    return [
        PerCanaryKL(
            canary_id=f"c{i}",
            kl_estimate=kl_val + np.random.uniform(-0.01, 0.01),
            log_p_target=-5.0,
            log_p_ref=-5.05,
            n_tokens=5,
            canary_type="T1_literal",
        )
        for i in range(n)
    ]


class TestTheorem5:
    """L_B ≤ min{B · D_KL^max, H(K)}."""

    def test_formula(self):
        cert = LeakageCertificate()
        B, K, kl_max = 1000, 10_000, 0.05
        result = cert._theorem5(B, kl_max, K)
        expected = B * kl_max
        assert abs(result - expected) < 1e-10

    def test_grows_linearly_with_budget(self):
        cert = LeakageCertificate()
        K, kl_max = 1000, 0.05
        c1 = cert._theorem5(100, kl_max, K)
        c2 = cert._theorem5(200, kl_max, K)
        assert abs(c2 / c1 - 2.0) < 1e-6

    def test_zero_kl_gives_zero_raw_leakage(self):
        cert = LeakageCertificate()
        result = cert._theorem5(10_000, 0.0, 1000)
        assert abs(result) < 1e-10


class TestTheorem7:
    """L_B ≤ B · E_π[D_KL] + H(K) — non-uniform prior"""

    def test_uniform_prior_matches_theorem5(self):
        cert = LeakageCertificate()
        K, B, kl = 100, 500, 0.03
        # Uniform prior → H(K) = log|K|, E_π[D_KL] = mean = kl
        t5 = cert._theorem5(B, kl, K)
        t7 = cert._theorem7(B, kl, math.log(K))
        assert abs(t5 - t7) < 1e-10

    def test_concentrated_prior_is_tighter(self):
        cert = LeakageCertificate()
        # Concentrated prior has lower entropy → tighter bound
        n = 100
        pi_uniform = np.ones(n) / n
        pi_conc = np.zeros(n)
        pi_conc[0] = 1.0  # all mass on one canary

        H_uniform = cert._entropy(pi_uniform)
        H_conc = cert._entropy(pi_conc)
        assert H_conc < H_uniform


class TestTheorem10:
    """Hoeffding concentration: L̂_B^{1-δ} = B(D̂_n + slack) + log|K|"""

    def test_slack_shrinks_with_more_canaries(self):
        cert = LeakageCertificate()
        B, kl_max, K, delta = 1000, 0.05, 10_000, 0.01
        _, c_small = cert._theorem10(B, 0.05, kl_max, n=100, K=K, delta=delta)
        _, c_large = cert._theorem10(B, 0.05, kl_max, n=10_000, K=K, delta=delta)
        assert c_large < c_small

    def test_hoeffding_slack_formula(self):
        cert = LeakageCertificate()
        kl_max, n, delta = 0.05, 1000, 0.01
        slack, _ = cert._theorem10(1000, 0.04, kl_max, n, 10_000, delta)
        expected_slack = kl_max * math.sqrt(math.log(2 / delta) / (2 * n))
        assert abs(slack - expected_slack) < 1e-10

    def test_certificate_valid_probability(self):
        """Raw certificate upper-bounds the KL estimate; public certificate respects H(K)."""
        np.random.seed(42)
        kl_results = make_kl_results(n=1000, kl_val=0.05)
        cert = LeakageCertificate()
        result = cert.compute(
            kl_results, query_budget=1000, canary_set_size=1000, delta=0.01
        )
        assert result.raw_hoeffding_certificate > result.mean_kl * 1000
        assert result.hoeffding_certificate <= result.prior_entropy
        assert result.entropy_cap_applied

    def test_compute_returns_all_fields(self):
        np.random.seed(0)
        kl_results = make_kl_results(50, 0.04)
        cert = LeakageCertificate()
        result = cert.compute(
            kl_results, query_budget=500, canary_set_size=500, delta=0.05
        )
        assert isinstance(result, CertificateResult)
        assert result.hoeffding_certificate > 0
        assert result.bernstein_certificate > 0
        assert result.extraction_prob_bound is not None
        assert 0.0 <= result.extraction_prob_bound <= 1.0


class TestTheorem17:
    """P(K̂=K) ≤ (L̂_B^{1-δ} + 1) / log|K|"""

    def test_corollary18(self):
        """Corollary 18: |K|=10^4, L̂=3.0 → bound = (3+1)/ln(10^4) ≈ 43.4%"""
        cert = LeakageCertificate()
        prob = cert._theorem17(certificate=3.0, K=10_000)
        # (3.0 + 1) / ln(10000) = 4 / 9.21 ≈ 0.4343 = 43.43%
        expected = 4.0 / math.log(10_000)
        assert abs(prob - expected) < 1e-6
        # Confirm the bound is ~43%, NOT sub-1% (common docstring error).
        # For sub-1% one needs L̂ < 0.01·log|K|−1 ≈ −0.91 nats — impossible.
        assert prob > 0.40

    def test_bound_at_most_one(self):
        cert = LeakageCertificate()
        # Large certificate should still be bounded by 1
        prob = cert._theorem17(1000.0, K=10)
        assert prob <= 1.0

    def test_smaller_cert_means_lower_extraction_prob(self):
        cert = LeakageCertificate()
        K = 10_000
        p1 = cert._theorem17(1.0, K)
        p2 = cert._theorem17(5.0, K)
        assert p1 < p2


class TestVacuous:
    def test_cert_above_log_K_is_vacuous(self):
        K = 1000
        assert LeakageCertificate.is_vacuous(math.log(K) + 0.1, K)

    def test_cert_below_log_K_is_valid(self):
        K = 1000
        assert not LeakageCertificate.is_vacuous(math.log(K) - 0.1, K)


class TestDPComposition:
    def test_dp_bound_formula(self):
        """DP bound = min{B · ε²/2, log|K|}"""
        eps, B, K = 8.0, 10_000, 10_000
        result = LeakageCertificate.dp_composition_certificate(eps, B, K)
        expected = min(B * eps**2 / 2, math.log(K))
        assert abs(result - expected) < 1e-10

    def test_leakcert_tighter_than_dp_for_large_eps(self):
        """For ε=8, LEAKCERT should be tighter than the analytic DP bound."""
        np.random.seed(42)
        # Simulate KL estimates consistent with ε=8 DP model
        # D_KL per query ≈ ε²/2 in the worst case; typically much smaller
        kl_results = make_kl_results(1000, kl_val=0.05)
        cert_computer = LeakageCertificate()
        result = cert_computer.compute(
            kl_results, query_budget=10_000, canary_set_size=10_000, delta=0.01
        )

        dp_bound = LeakageCertificate.dp_composition_certificate(8.0, 10_000, 10_000)
        # LeakCert certificate should be << DP bound for typical empirical KL
        assert result.hoeffding_certificate < dp_bound
