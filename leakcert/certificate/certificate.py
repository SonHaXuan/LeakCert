"""
Leakage certificate computation.

Implements the five core theorems from Section 3 of the study:

  Theorem 5  : Query-budget leakage upper bound (uniform prior)
               L_B ≤ B · D_KL(p_K ‖ q_K) + log|K|

  Theorem 7  : Non-uniform prior generalisation
               L_B ≤ B · E_π[D_KL(p_k ‖ q_k)] + H(K)

  Theorem 10 : Black-box Hoeffding concentration
               L̂_B^{1-δ} = B(D̂_KL_n + κ_max √(log(2/δ)/(2n))) + log|K|

  Theorem 13 : MI-surrogate Bernstein concentration (tighter for small σ²)
               L̂_B^{1-δ} = B(D̂_KL_n + σ√(2log(2/δ)/n)) + H(K)

  Theorem 17 : Adaptive-attacker extraction probability bound
               P(K̂=K) ≤ (L̂_B^{1-δ} + 1) / log|K|

All quantities are in nats (natural logarithm).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .kl_estimator import PerCanaryKL


@dataclass
class CertificateResult:
    """
    Full certificate for a deployed model at a given query budget B.

    All values in nats.
    """

    query_budget: int                   # B
    canary_set_size: int                # |K|
    confidence: float                   # 1 - δ
    delta: float                        # δ

    # Theorem 5 / 7 (population)
    population_certificate: float       # B · D_KL^max + log|K|   (Theorem 5)
    nonuniform_certificate: float       # B · E_π[D_KL] + H(K)    (Theorem 7)

    # Theorem 10 (Hoeffding concentration)
    hoeffding_certificate: float        # L̂_B^{1-δ} (Theorem 10)
    hoeffding_slack: float

    # Theorem 13 (Bernstein concentration)
    bernstein_certificate: float        # L̂_B^{1-δ} (Theorem 13)
    bernstein_slack: float

    # Statistics
    n_canaries: int
    mean_kl: float
    max_kl: float
    std_kl: float
    prior_entropy: float                # H(K)

    # Empirical MI for tightness ratio
    empirical_mi: Optional[float] = None
    tightness_ratio: Optional[float] = None

    # Extraction probability bound (Theorem 17 / Corollary 18)
    extraction_prob_bound: Optional[float] = None

    # Certified extraction advantage over random baseline (Definition: study §3.5)
    # advantage = extraction_prob_bound / (1/|K|) = extraction_prob_bound * |K|
    # Interpretation: how many times more likely the adversary can extract
    # compared to random guessing.  1.0 = no advantage; ∞ = vacuous.
    # NOTE: The Fano-based bound is inherently loose for moderate |K|.
    # Even L̂=0 gives extraction_prob_bound = 1/log|K| >> 1/|K|.
    # The advantage metric is the meaningful comparison across defences.
    certified_extraction_advantage: Optional[float] = None

    def summary(self) -> str:
        lines = [
            f"LeakCert Certificate  B={self.query_budget}, |K|={self.canary_set_size}, "
            f"confidence={self.confidence:.2%}",
            f"  Hoeffding certificate : {self.hoeffding_certificate:.3f} nats",
            f"  Bernstein certificate : {self.bernstein_certificate:.3f} nats",
            f"  Population bound      : {self.population_certificate:.3f} nats",
            f"  Mean KL               : {self.mean_kl:.4f} nats",
            f"  Max  KL               : {self.max_kl:.4f} nats",
            f"  Prior entropy H(K)    : {self.prior_entropy:.3f} nats",
        ]
        if self.empirical_mi is not None:
            lines.append(f"  Empirical MI          : {self.empirical_mi:.3f} nats")
            lines.append(f"  Tightness ratio       : {self.tightness_ratio:.3f}×")
        if self.extraction_prob_bound is not None:
            lines.append(
                f"  Extraction prob bound : {self.extraction_prob_bound:.4%}"
                f"  (random baseline: {1/self.canary_set_size:.4%})"
            )
        if self.certified_extraction_advantage is not None:
            lines.append(
                f"  Certified advantage   : {self.certified_extraction_advantage:.1f}×"
                f" over random guessing"
            )
        return "\n".join(lines)


class LeakageCertificate:
    """
    Computes leakage certificates from per-canary KL estimates.

    Usage
    -----
    kl_results = estimator.estimate_panel(panel)
    cert = LeakageCertificate()
    result = cert.compute(kl_results, query_budget=10_000, canary_set_size=10_000)
    print(result.summary())
    """

    # ------------------------------------------------------------------
    # Main computation
    # ------------------------------------------------------------------

    def compute(
        self,
        kl_results: list[PerCanaryKL],
        query_budget: int,
        canary_set_size: int,
        delta: float = 0.01,
        prior: Optional[list[float]] = None,
        empirical_mi: Optional[float] = None,
    ) -> CertificateResult:
        """
        Compute the full certificate from per-canary KL estimates.

        Parameters
        ----------
        kl_results       : list of PerCanaryKL from KLEstimator.estimate_panel
        query_budget     : B (max adaptive queries per API key)
        canary_set_size  : |K|
        delta            : confidence parameter (δ); certificate holds w.p. ≥ 1-δ
        prior            : π(k) for non-uniform generalisation (uniform if None)
        empirical_mi     : Î(K;Y^B) from MINE, for tightness ratio
        """
        if not kl_results:
            raise ValueError("kl_results is empty")

        kl_values = np.array([r.kl_estimate for r in kl_results])
        n = len(kl_values)
        B = query_budget
        K = canary_set_size

        mean_kl = float(np.mean(kl_values))
        max_kl = float(np.max(kl_values))
        std_kl = float(np.std(kl_values))
        kappa_max = max_kl

        # ------------------------------------------------------------------
        # Theorem 5 (population upper bound, uniform prior)
        # L_B ≤ B · D_KL^max + log|K|
        # ------------------------------------------------------------------
        pop_cert = self._theorem5(B, kappa_max, K)

        # ------------------------------------------------------------------
        # Theorem 7 (non-uniform prior)
        # L_B ≤ B · E_π[D_KL] + H(K)
        # ------------------------------------------------------------------
        if prior is None:
            prior = [1.0 / n] * n
        pi = np.array(prior)
        pi = pi / pi.sum()   # normalise
        prior_entropy = self._entropy(pi)
        weighted_kl = float(np.dot(pi, kl_values))
        nonuniform_cert = self._theorem7(B, weighted_kl, prior_entropy)

        # ------------------------------------------------------------------
        # Theorem 10 (Hoeffding concentration, black-box)
        # L̂_B^{1-δ} = B(D̂_KL_n + κ_max √(log(2/δ)/(2n))) + log|K|
        # ------------------------------------------------------------------
        hoeffding_slack, hoeffding_cert = self._theorem10(
            B, mean_kl, kappa_max, n, K, delta
        )

        # ------------------------------------------------------------------
        # Theorem 13 (Bernstein / MI-surrogate, tighter)
        # L̂_B^{1-δ} = B(D̂_KL_n + σ√(2log(2/δ)/n)) + H(K)
        # ------------------------------------------------------------------
        sigma = std_kl   # empirical std as σ estimate (Assumption 12)
        bernstein_slack, bernstein_cert = self._theorem13(
            B, mean_kl, sigma, n, prior_entropy, delta
        )

        # ------------------------------------------------------------------
        # Extraction probability bound (Theorem 17 / Corollary 18)
        # P(K̂=K) ≤ (L̂_B^{1-δ} + 1) / log|K|
        # ------------------------------------------------------------------
        cert_for_extraction = min(hoeffding_cert, bernstein_cert)
        extraction_bound = self._theorem17(cert_for_extraction, K)
        # Certified extraction advantage = bound / random-guess baseline (1/K)
        # This is the meaningful comparison: how much worse is a certified
        # attack compared to random guessing?
        random_baseline = 1.0 / K if K > 0 else 1.0
        certified_advantage = extraction_bound / random_baseline   # dimensionless

        # ------------------------------------------------------------------
        # Tightness ratio
        # ------------------------------------------------------------------
        tightness = None
        if empirical_mi is not None and empirical_mi > 0:
            tightness = hoeffding_cert / empirical_mi

        return CertificateResult(
            query_budget=B,
            canary_set_size=K,
            confidence=1 - delta,
            delta=delta,
            population_certificate=pop_cert,
            nonuniform_certificate=nonuniform_cert,
            hoeffding_certificate=hoeffding_cert,
            hoeffding_slack=hoeffding_slack,
            bernstein_certificate=bernstein_cert,
            bernstein_slack=bernstein_slack,
            n_canaries=n,
            mean_kl=mean_kl,
            max_kl=max_kl,
            std_kl=std_kl,
            prior_entropy=prior_entropy,
            empirical_mi=empirical_mi,
            tightness_ratio=tightness,
            extraction_prob_bound=extraction_bound,
            certified_extraction_advantage=certified_advantage,
        )

    # ------------------------------------------------------------------
    # Theorem implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _theorem5(B: int, kl_max: float, K: int) -> float:
        """
        Theorem 5: L_B(M_θ, A) ≤ B · D_KL(p_K ‖ q_K) + log|K|

        The per-query KL upper bound comes from the data-processing inequality
        applied to the chain rule for mutual information.  The log|K| term is
        a Fano correction for the maximum entropy of the uniform prior on K.
        """
        return B * kl_max + math.log(K)

    @staticmethod
    def _theorem7(B: int, weighted_kl: float, prior_entropy: float) -> float:
        """
        Theorem 7: L_B ≤ B · E_π[D_KL(p_k ‖ q_k)] + H(K)

        Non-uniform prior generalisation. H(K) = -Σ π(k) log π(k) is tighter
        than log|K| when the prior is concentrated (low entropy).
        """
        return B * weighted_kl + prior_entropy

    @staticmethod
    def _theorem10(
        B: int, mean_kl: float, kappa_max: float, n: int, K: int, delta: float
    ) -> tuple[float, float]:
        """
        Theorem 10 (Hoeffding concentration):
            L̂_B^{1-δ} = B(D̂_KL_n + κ_max √(log(2/δ)/(2n))) + log|K|

        The certificate upper-bounds L_B with probability ≥ 1-δ.
        The slack is κ_max · √(log(2/δ)/(2n)).
        """
        slack = kappa_max * math.sqrt(math.log(2.0 / delta) / (2.0 * n))
        cert = B * (mean_kl + slack) + math.log(K)
        return slack, cert

    @staticmethod
    def _theorem13(
        B: int,
        mean_kl: float,
        sigma: float,
        n: int,
        prior_entropy: float,
        delta: float,
    ) -> tuple[float, float]:
        """
        Theorem 13 (Bernstein-style concentration, MI-surrogate):
            L̂_B^{1-δ} = B(D̂_KL_n + σ√(2log(2/δ)/n)) + H(K)

        Uses the bounded variance assumption (Assumption 12) for a tighter
        O(n^{-1/2}) convergence rate with a Bernstein constant σ instead of κ_max.
        """
        slack = sigma * math.sqrt(2.0 * math.log(2.0 / delta) / n)
        cert = B * (mean_kl + slack) + prior_entropy
        return slack, cert

    @staticmethod
    def _theorem17(certificate: float, K: int) -> float:
        """
        Theorem 17 / Corollary 18: adaptive-attacker extraction probability bound.

            P(K̂ = K) ≤ (L̂_B^{1-δ} + 1) / log|K|

        The "+1" accounts for H_b(P_e) ≤ log 2 < 1 nat in Fano's inequality.

        Example (Corollary 18): |K|=10^4, L̂=3.0 nats
          → P(K̂=K) ≤ (3.0+1)/ln(10^4) = 4/9.21 ≈ 43.4%

        Note: to achieve a tight bound below, say, 1% extraction probability,
        the certificate must satisfy L̂ < 0.01·log|K| − 1 nats.  For |K|=10^4
        that requires L̂ < −0.91 nats, which is impossible since L̂ ≥ 0.  The
        useful regime of this corollary is therefore |K| ≥ e^{(L̂+1)/p_target}
        for a target success probability p_target, or equivalently, large K
        paired with small per-query KL.
        """
        log_K = math.log(K)
        if log_K <= 0:
            return 1.0
        return min(1.0, (certificate + 1.0) / log_K)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _entropy(pi: np.ndarray) -> float:
        """Shannon entropy H(K) = -Σ π(k) log π(k) in nats."""
        pi = pi[pi > 0]
        return float(-np.sum(pi * np.log(pi)))

    # ------------------------------------------------------------------
    # Certificate sweep over budgets (for Table 1 / Figure 2)
    # ------------------------------------------------------------------

    def compute_sweep(
        self,
        kl_results: list[PerCanaryKL],
        budgets: list[int],
        canary_set_size: int,
        delta: float = 0.01,
        prior: Optional[list[float]] = None,
    ) -> list[CertificateResult]:
        """
        Compute certificates for a range of query budgets.
        Returns one CertificateResult per budget value.
        Reproduces Table 1 and Figure 2 from the study.
        """
        return [
            self.compute(kl_results, B, canary_set_size, delta, prior)
            for B in budgets
        ]

    # ------------------------------------------------------------------
    # Vacuous certificate check
    # ------------------------------------------------------------------

    @staticmethod
    def is_vacuous(certificate: float, K: int) -> bool:
        """
        A certificate is vacuous if it exceeds log|K| (the trivial upper bound).
        This happens when B → ∞ (Section 5.10).
        """
        return certificate >= math.log(K)

    # ------------------------------------------------------------------
    # DP composition bound (Theorem 5 + DP)
    # ------------------------------------------------------------------

    @staticmethod
    def dp_composition_certificate(
        epsilon: float, query_budget: int, canary_set_size: int
    ) -> float:
        """
        Analytic DP bound for a (ε,δ)-DP model (Section 5.7):
            I(K; Y^B) ≤ B · ε²/2     (Rényi DP composition)

        Used for comparison with LEAKCERT in Table 8.
        """
        return query_budget * (epsilon ** 2) / 2.0 + math.log(canary_set_size)
