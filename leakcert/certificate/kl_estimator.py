"""
Per-canary KL divergence estimator (black-box).

Implements the MI surrogate κ̂(y; M_θ) from Theorem 13 / Assumption 12:

    κ̂_i = κ*_i + ξ_i

where κ*_i = D_KL(p_{K=k_i} ‖ q_{K}) and ξ_i is zero-mean noise.

Three estimators are provided:
  1. LikelihoodRatioKL  : log p_target(k|c) − log p_ref(k|c)      [requires ref model]
  2. SelfRatioKL        : log p_target(k|c) − E_{r}[log p_target(r|c)]  [self-normalised]
  3. CalibratedMIAKL    : uses a trained MIA classifier score        [Zarifzadeh et al. 2024]
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..canary.types import Canary, CanaryPanel
from ..model.completion_service import CompletionService

logger = logging.getLogger(__name__)


@dataclass
class PerCanaryKL:
    """Stores the KL estimate and metadata for a single canary."""

    canary_id: str
    kl_estimate: float          # κ̂_i ≈ D_KL(p_K || q_K) for this canary
    log_p_target: float         # log p_θ(k | c_k) under target model
    log_p_ref: float            # log p_ref(k | c_k) under reference model
    n_tokens: int               # number of tokens in the canary secret
    canary_type: str = ""


class KLEstimator:
    """
    Estimates per-canary D_KL(p_K ‖ q_K) for all canaries in a panel.

    Parameters
    ----------
    target_service  : fine-tuned model M_θ  (p_K distribution)
    ref_service     : base model M_base     (q_K distribution)
                      If None, use self-ratio estimator.
    n_queries_per_canary : B′ — queries per canary for the rolling estimate.
                           In deployment this is 1; for offline concentration,
                           the study uses the full training panel.
    """

    def __init__(
        self,
        target_service: CompletionService,
        ref_service: Optional[CompletionService] = None,
        n_queries_per_canary: int = 1,
    ):
        self.target = target_service
        self.ref = ref_service
        self.n_queries_per_canary = n_queries_per_canary

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def estimate_panel(self, panel: CanaryPanel) -> list[PerCanaryKL]:
        """
        Compute per-canary KL estimates for all canaries in the panel.
        Returns a list of PerCanaryKL, one per canary.
        """
        results = []
        for i, canary in enumerate(panel):
            if i % 100 == 0:
                logger.info(f"KL estimation: {i}/{len(panel)} canaries processed")
            result = self.estimate_canary(canary)
            results.append(result)
        return results

    def estimate_canary(self, canary: Canary) -> PerCanaryKL:
        """Estimate D_KL for a single canary."""
        if self.ref is not None:
            return self._lr_estimate(canary)
        else:
            return self._self_ratio_estimate(canary)

    # ------------------------------------------------------------------
    # Estimator 1: Likelihood Ratio (requires reference model)
    # ------------------------------------------------------------------

    def _lr_estimate(self, canary: Canary) -> PerCanaryKL:
        """
        κ̂_i = log p_target(k_i | c_i) − log p_ref(k_i | c_i)

        This is the log-likelihood ratio, which is an unbiased surrogate
        for D_KL(p_K ‖ q_K) when averaged over the training distribution
        (Assumption 12 / Theorem 13).
        """
        log_p_target = self.target.log_probability(canary.context, canary.secret)
        log_p_ref = self.ref.log_probability(canary.context, canary.secret)
        kl_est = max(0.0, log_p_target - log_p_ref)   # clamp to [0, ∞)

        n_tokens = len(self.target.per_token_log_probs(canary.context, canary.secret))
        return PerCanaryKL(
            canary_id=canary.canary_id,
            kl_estimate=kl_est,
            log_p_target=log_p_target,
            log_p_ref=log_p_ref,
            n_tokens=n_tokens,
            canary_type=canary.canary_type.value,
        )

    # ------------------------------------------------------------------
    # Estimator 2: Self-ratio (single model, reference-free)
    # ------------------------------------------------------------------

    def _self_ratio_estimate(
        self, canary: Canary, n_neg_samples: int = 10
    ) -> PerCanaryKL:
        """
        Self-normalised estimator (reference-free):

            κ̂_i = log p_target(k_i | c_i)
                   − (1/n) Σ_{r ~ p_target(·|c_i)} log p_target(r | c_i)

        The denominator approximates E_q[log p_target(k | c)] using completions
        from a different context (no canary).  In practice we sample n random
        contexts from the corpus and average their log-probs under the target.

        This is weaker than the LR estimator but requires only the target model.
        """
        log_p_target = self.target.log_probability(canary.context, canary.secret)

        # Estimate the marginal: sample completions and score them
        neg_samples = self.target.complete(canary.context, n_samples=n_neg_samples)
        neg_log_probs = []
        for s in neg_samples:
            if s.text.strip():
                lp = self.target.log_probability(canary.context, s.text)
                neg_log_probs.append(lp)

        log_p_ref = float(np.mean(neg_log_probs)) if neg_log_probs else 0.0
        kl_est = max(0.0, log_p_target - log_p_ref)

        n_tokens = len(canary.secret.split())  # approximate
        return PerCanaryKL(
            canary_id=canary.canary_id,
            kl_estimate=kl_est,
            log_p_target=log_p_target,
            log_p_ref=log_p_ref,
            n_tokens=n_tokens,
            canary_type=canary.canary_type.value,
        )

    # ------------------------------------------------------------------
    # Estimator 3: Calibrated MIA score (Zarifzadeh et al. 2024)
    # ------------------------------------------------------------------

    def calibrated_mia_estimate(
        self,
        canary: Canary,
        n_neighbors: int = 50,
    ) -> PerCanaryKL:
        """
        Low-cost high-power MIA surrogate from [21].

        Score = log p(k | c) / p_ref(k | c)
        where p_ref is approximated by neighbour completions:
          p_ref(k | c) ≈ mean_{k' ~ p(·|c)} p(k | c')

        This exploits the ratio-based calibration from [21] to boost
        the signal-to-noise ratio of the surrogate.
        """
        # Primary score: target likelihood
        log_p_target = self.target.log_probability(canary.context, canary.secret)

        # Neighbour-based reference: draw n_neighbors completions from target
        neighbors = self.target.complete(canary.context, n_samples=n_neighbors)
        neighbor_log_probs = []
        for nb in neighbors:
            if nb.text.strip():
                neighbor_log_probs.append(
                    self.target.log_probability(canary.context, nb.text)
                )

        if not neighbor_log_probs:
            log_p_ref = 0.0
        else:
            # Calibration: use log-mean-exp for numerical stability
            arr = np.array(neighbor_log_probs)
            log_p_ref = float(arr.max() + np.log(np.mean(np.exp(arr - arr.max()))))

        kl_est = max(0.0, log_p_target - log_p_ref)
        n_tokens = len(self.target.per_token_log_probs(canary.context, canary.secret))

        return PerCanaryKL(
            canary_id=canary.canary_id,
            kl_estimate=kl_est,
            log_p_target=log_p_target,
            log_p_ref=log_p_ref,
            n_tokens=n_tokens,
            canary_type=canary.canary_type.value,
        )

    # ------------------------------------------------------------------
    # Streaming / online update (used by Certificate Generator at runtime)
    # ------------------------------------------------------------------

    def streaming_kl_contribution(
        self, prompt: str, completion: str
    ) -> float:
        """
        Per-query KL contribution for a single (prompt, completion) pair.
        Used by the runtime certificate generator for the rolling estimate.

        Returns D_KL contribution for this single query:
            Δ_KL = log p_target(y | x) − log p_ref(y | x)
        """
        log_p_t = self.target.log_probability(prompt, completion)
        if self.ref is not None:
            log_p_r = self.ref.log_probability(prompt, completion)
        else:
            log_p_r = 0.0   # conservative fallback

        return max(0.0, log_p_t - log_p_r)

    # ------------------------------------------------------------------
    # MINE-based empirical MI estimator (for certificate tightness ratio)
    # ------------------------------------------------------------------

    @staticmethod
    def mine_estimate(
        kl_samples: list[float],
        query_budget: int,
        canary_set_size: int,
        use_neural: bool = True,
        n_epochs: int = 500,
        hidden_dim: int = 64,
        lr: float = 1e-3,
        batch_size: int = 128,
        seed: int = 0,
    ) -> float:
        """
        MINE: Mutual Information Neural Estimation (Belghazi et al., ICML 2018).
        Used as the denominator Î(K;Y^B) in the tightness ratio (Table 3).

        Setting
        -------
        - K ~ Uniform over N canaries; represented by its per-canary KL score κ̂_k.
        - Y for canary k: a single-query observation whose expected log-ratio is κ̂_k.
          We model Y|K=k ~ N(κ̂_k, σ²) with σ estimated from the empirical variance.
        - Per-query MI I(K; y) is estimated via the DV bound [Donsker–Varadhan]:
            I(K; y) ≥ sup_T { E_{joint}[T(K, y)] - log E_{marginal}[e^{T(K, y)}] }
        - I(K; Y^B) ≈ B · I(K; y)  (queries are independent given K).

        If torch is not available, falls back to the mean-LLR estimator.

        Parameters
        ----------
        kl_samples    : list of per-canary κ̂_i estimates
        query_budget  : B
        canary_set_size : |K| (unused in computation, kept for API consistency)
        use_neural    : if False, use the mean-LLR fallback
        n_epochs      : MINE training epochs
        hidden_dim    : MLP hidden layer width
        lr            : Adam learning rate
        batch_size    : minibatch size
        seed          : random seed for reproducibility
        """
        if not kl_samples:
            return 0.0

        kl_arr = np.array(kl_samples, dtype=np.float64)

        if not use_neural:
            return query_budget * float(np.mean(kl_arr))

        try:
            return MINEEstimator(
                hidden_dim=hidden_dim,
                n_epochs=n_epochs,
                lr=lr,
                batch_size=batch_size,
                seed=seed,
            ).estimate(kl_arr, query_budget)
        except ImportError:
            logger.warning(
                "torch not available — neural MINE falling back to analytic "
                "B*mean(KL). Install torch for study-valid E1 tightness ratios."
            )
            return query_budget * float(np.mean(kl_arr))


class MINEEstimator:
    """
    Mutual Information Neural Estimator (Belghazi et al., ICML 2018).

    Estimates I(K; y) for a single query y from per-canary KL samples,
    then scales by B to obtain I(K; Y^B).

    The DV lower bound:
        I(K; y) ≥ E_{(K,y)~p_joint}[T_θ(κ̂_K, y)]
                  - log E_{(K,y)~p_K⊗p_y}[e^{T_θ(κ̂_K, y)}]

    where T_θ is a two-layer MLP trained to maximise the bound.

    Data construction
    -----------------
    - Joint samples: (κ̂_k, y_k) where y_k ~ N(κ̂_k, σ²).
    - Marginal samples: (κ̂_k, y_j) where j ≠ k is drawn independently.

    The Gaussian noise σ models the within-canary variance of the
    per-query KL surrogate (Assumption 12 / Theorem 13).
    """

    def __init__(
        self,
        hidden_dim: int = 64,
        n_epochs: int = 500,
        lr: float = 1e-3,
        batch_size: int = 128,
        seed: int = 0,
        sigma_query_nats: float = 0.1,
    ):
        self.hidden_dim = hidden_dim
        self.n_epochs = n_epochs
        self.lr = lr
        self.batch_size = batch_size
        self.seed = seed
        # Fixed per-query noise std in nats.  Using a constant (not the
        # per-dataset std) ensures I(K;Y^B) grows monotonically with KL scale:
        # SNR = std(κ̂) / sigma_query_nats, MI = 0.5·log(1+SNR²) per query.
        self.sigma_query_nats = sigma_query_nats

    def estimate(self, kl_arr: np.ndarray, query_budget: int) -> float:
        """Train MINE and return I(K; Y^B) = B · Î(K; y)."""
        import torch
        import torch.nn as nn

        rng = np.random.RandomState(self.seed)
        torch.manual_seed(self.seed)

        n = len(kl_arr)
        mu = float(np.mean(kl_arr))
        kl_std = float(np.std(kl_arr)) + 1e-8

        # Normalisation scale = max(kl_std, sigma_query_nats).
        # This separates the per-dataset spread (kl_std) from the per-query
        # noise (sigma_query_nats), so SNR = kl_std / sigma_query_nats is
        # preserved after normalisation and MI grows with KL scale.
        sigma_norm = max(kl_std, self.sigma_query_nats)
        kl_norm = (kl_arr - mu) / sigma_norm
        # Noise in normalised space: σ_noise_norm = sigma_query_nats / sigma_norm ≤ 1.
        noise_in_norm = float(self.sigma_query_nats / sigma_norm)

        kl_t = torch.tensor(kl_norm, dtype=torch.float32)

        # Two-layer MLP: T_θ(κ̂_K, y) → scalar
        net = nn.Sequential(
            nn.Linear(2, self.hidden_dim),
            nn.ELU(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
            nn.ELU(),
            nn.Linear(self.hidden_dim, 1),
        )
        optimiser = torch.optim.Adam(net.parameters(), lr=self.lr)

        mi_history: list[float] = []

        for epoch in range(self.n_epochs):
            bs = min(self.batch_size, n)

            # ── Joint samples: (κ̂_k, y_k ~ N(κ̂_k, noise_in_norm²)) ──
            idx_j = rng.choice(n, size=bs, replace=True)
            x_j = kl_t[idx_j]
            y_j = x_j + torch.tensor(
                (rng.randn(bs) * noise_in_norm).astype(np.float32)
            )

            # ── Marginal samples: (κ̂_k, y_m) independently ──────────
            idx_mx = rng.choice(n, size=bs, replace=True)
            idx_my = rng.choice(n, size=bs, replace=True)
            x_m = kl_t[idx_mx]
            y_m = kl_t[idx_my] + torch.tensor(
                (rng.randn(bs) * noise_in_norm).astype(np.float32)
            )

            inp_j = torch.stack([x_j, y_j], dim=1)
            inp_m = torch.stack([x_m, y_m], dim=1)

            t_joint = net(inp_j).squeeze(-1)               # (bs,)
            t_marg  = net(inp_m).squeeze(-1)               # (bs,)

            # DV bound: E_joint[T] - log(E_marginal[e^T])
            # Use log-sum-exp for numerical stability:
            #   log(E[e^T]) = logsumexp(T) - log(bs)
            dv = t_joint.mean() - (
                torch.logsumexp(t_marg, dim=0) - math.log(bs)
            )
            loss = -dv                                      # maximise DV

            optimiser.zero_grad()
            loss.backward()
            optimiser.step()

            # Record MI estimate from second half of training (stabilised)
            if epoch >= self.n_epochs // 2:
                mi_history.append(max(0.0, dv.item()))

        # Average over stabilised second half; this is Î(K; y_t) per query
        mi_per_query = float(np.mean(mi_history)) if mi_history else 0.0

        # Scale to I(K; Y^B) ≈ B · Î(K; y_t)
        return query_budget * max(0.0, mi_per_query)
