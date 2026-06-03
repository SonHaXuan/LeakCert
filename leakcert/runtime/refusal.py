"""
Uncertainty-aware refusal classifier (Section 3.7).

A small classifier φ_u(y) ∈ [0, 1] scores the likelihood that output y is
a memorised canary.  Outputs above a threshold τ are replaced with a refusal
token ⊥.  The classifier is itself audited (i.e., it cannot introduce new
leakage).

The study targets a 1% refusal rate on a held-out completion set (Section 4.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np


# ---------------------------------------------------------------------------
# Secret-pattern heuristics (fast pre-filter)
# ---------------------------------------------------------------------------

_AWS_KEY_RE = re.compile(r'AKIA[0-9A-Z]{16}')
_JWT_RE = re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}')
_RSA_PREFIX_RE = re.compile(r'-----BEGIN (RSA )?PRIVATE KEY-----')
_LICENCE_RE = re.compile(r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}')
_PRIVATE_RE = re.compile(r'(password|secret|token|key)\s*=\s*["\'][A-Za-z0-9+/]{16,}', re.I)

_HARD_HEURISTIC_PATTERNS = [
    _AWS_KEY_RE, _JWT_RE, _RSA_PREFIX_RE, _LICENCE_RE
]


@dataclass
class RefusalDecision:
    should_refuse: bool
    score: float
    reason: str = ""


class UncertaintyRefusal:
    """
    Uncertainty-aware refusal module.

    Combines:
      1. Fast heuristic pattern matching (deterministic, high recall for T1)
      2. A learned logistic-regression classifier trained on token-level features
         (targets 1% FPR on held-out completions)

    Parameters
    ----------
    threshold   : φ_u score above which a completion is refused.
    use_learned : if True, use a learned classifier in addition to heuristics.
    """

    def __init__(
        self,
        threshold: float = 0.5,
        use_learned: bool = True,
        use_heuristics: bool = True,
    ):
        self.threshold = threshold
        self.use_learned = use_learned
        self.use_heuristics = use_heuristics
        self._classifier = None   # loaded lazily or trained externally

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def score(self, completion: str) -> float:
        """
        Compute φ_u(y) ∈ [0, 1].
        Returns a probability that `completion` is a memorised canary.
        """
        # Fast heuristic score
        heuristic_score = self._heuristic_score(completion) if self.use_heuristics else 0.0
        if heuristic_score >= 1.0:
            return 1.0

        if self.use_learned and self._classifier is not None:
            learned_score = self._learned_score(completion)
            return max(heuristic_score, learned_score)

        return heuristic_score

    def decide(self, completion: str) -> RefusalDecision:
        """Return a refusal decision for `completion`."""
        s = self.score(completion)
        if s >= self.threshold:
            return RefusalDecision(should_refuse=True, score=s, reason="high_canary_score")
        return RefusalDecision(should_refuse=False, score=s)

    # ------------------------------------------------------------------
    # Heuristic scoring
    # ------------------------------------------------------------------

    def _heuristic_score(self, text: str) -> float:
        """Score based on secret-pattern regex matching."""
        for pattern in _HARD_HEURISTIC_PATTERNS:
            if pattern.search(text):
                return 1.0
        # Generic key/token/password assignments are useful weak evidence, but
        # treating them as certain canaries creates many W3 false refusals for
        # ordinary code-completion tasks.
        if _PRIVATE_RE.search(text):
            return 0.7
        return 0.0

    # ------------------------------------------------------------------
    # Learned classifier
    # ------------------------------------------------------------------

    def _learned_score(self, text: str) -> float:
        """
        Score using the trained logistic-regression classifier.
        Features: token-level entropy, avg token length, n-gram overlap with
        known secret vocabularies.
        """
        if self._classifier is None:
            return 0.0
        features = self._extract_features(text)
        prob = self._classifier.predict_proba([features])[0][1]
        return float(prob)

    @staticmethod
    def _extract_features(text: str) -> list[float]:
        """Extract numeric features for the learned classifier."""
        tokens = text.split()
        n_tokens = max(len(tokens), 1)

        # Feature 1: average token length (secrets tend to be long tokens)
        avg_len = sum(len(t) for t in tokens) / n_tokens

        # Feature 2: fraction of uppercase characters
        upper_frac = sum(1 for c in text if c.isupper()) / max(len(text), 1)

        # Feature 3: fraction of digits
        digit_frac = sum(1 for c in text if c.isdigit()) / max(len(text), 1)

        # Feature 4: presence of special secret-like delimiters
        has_eq = float("=" in text)
        has_quote = float('"' in text or "'" in text)
        has_dash = float("-" in text)

        # Feature 5: token entropy (high entropy → likely random secret)
        char_counts = {}
        for c in text:
            char_counts[c] = char_counts.get(c, 0) + 1
        total = len(text) or 1
        entropy = -sum(
            (cnt / total) * np.log2(cnt / total) for cnt in char_counts.values()
        )

        return [avg_len, upper_frac, digit_frac, has_eq, has_quote, has_dash, entropy]

    def train(
        self,
        positive_examples: list[str],   # canary completions
        negative_examples: list[str],   # normal completions
    ) -> None:
        """
        Train the logistic-regression classifier.
        Targets ≤1% FPR (refusal rate on W3) per the study's configuration.
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline

        X = [self._extract_features(t) for t in positive_examples + negative_examples]
        y = [1] * len(positive_examples) + [0] * len(negative_examples)
        self._classifier = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
        ])
        self._classifier.fit(X, y)

    # ------------------------------------------------------------------
    # Threshold calibration (study: tuned to 1% refusal rate, §4.2)
    # ------------------------------------------------------------------

    def calibrate_threshold(
        self,
        held_out_completions: list[str],
        target_refusal_rate: float = 0.01,
    ) -> float:
        """
        Auto-tune the refusal threshold τ so that the fraction of legitimate
        (W3) completions replaced with ⊥ is ≤ target_refusal_rate.

        study setting: 1% refusal rate on the W3 held-out completion set.

        Strategy: binary search over τ ∈ [0, 1].
        The threshold is set to the (1 - target_rate) quantile of the score
        distribution on held-out completions.

        Parameters
        ----------
        held_out_completions : W3 completions (legitimate, non-canary).
        target_refusal_rate  : desired maximum FPR (default 1%).

        Returns
        -------
        New threshold value (also stored in self.threshold).
        """
        if not held_out_completions:
            return self.threshold

        scores = np.array([self.score(c) for c in held_out_completions])
        # threshold = quantile such that at most target_rate fraction exceeds it
        quantile = 1.0 - target_refusal_rate
        new_threshold = float(np.quantile(scores, quantile))
        # Safety: never go below 0.1 to avoid refusing everything
        new_threshold = max(0.1, min(new_threshold, 0.999))
        self.threshold = new_threshold
        return new_threshold

    def expected_refusal_rate(self, held_out_completions: list[str]) -> float:
        """Estimate refusal rate on a set of legitimate completions."""
        if not held_out_completions:
            return 0.0
        refused = sum(
            1 for c in held_out_completions if self.decide(c).should_refuse
        )
        return refused / len(held_out_completions)

    def save(self, path: str) -> None:
        import pickle
        with open(path, "wb") as f:
            pickle.dump({"classifier": self._classifier, "threshold": self.threshold}, f)

    def load(self, path: str) -> None:
        import pickle
        with open(path, "rb") as f:
            state = pickle.load(f)
        if isinstance(state, dict):
            self._classifier = state.get("classifier")
            self.threshold = state.get("threshold", self.threshold)
        else:
            self._classifier = state
