"""
B5 – Content filter defence.

study (Section 4.2, B5):
  A high-recall regex bank (Meli et al. [28]) + a learned secret classifier
  (Saha et al. [30]) thresholded at 0.5.

Key finding (Section 5.5): content filter B5 loses 7.4× effectiveness under
paraphrase attacks (W5/W4 ratio = 7.42) because it depends on lexical form.
LEAKCERT loses only 1.05× because it operates on per-query KL divergence,
which paraphrase attacks still impose.
"""

from __future__ import annotations


from ..model.completion_service import CompletionResult
from .base import DefenseWrapper, DefenseConfig
from ..runtime.suppression import TargetStringSuppression

REFUSAL_TOKEN = "<|FILTERED|>"


class ContentFilterDefense(DefenseWrapper):
    """
    B5: Content filter — regex bank + learned classifier.

    Blocks completions that match any known secret pattern.
    Unlike LeakCert's target-string suppression (which is defence-in-depth),
    this IS the primary defence here.
    """

    def __init__(self, base_service, classifier_threshold: float = 0.5):
        config = DefenseConfig(
            name="B5_content_filter",
            description=f"Regex + learned classifier (threshold={classifier_threshold})",
        )
        super().__init__(base_service, config)
        self.threshold = classifier_threshold
        self._suppressor = TargetStringSuppression()
        self._classifier = None   # trained separately if available

    def complete(self, prompt: str, n_samples: int = 1) -> list[CompletionResult]:
        results = self.base.complete(prompt, n_samples)
        return self._filter_results(results)

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ) -> list[list[CompletionResult]]:
        batches = self.base.complete_many(prompts, n_samples=n_samples, batch_size=batch_size)
        return [self._filter_results(results) for results in batches]

    def _filter_results(self, results: list[CompletionResult]) -> list[CompletionResult]:
        filtered = []
        for r in results:
            if self._is_secret(r.text):
                filtered.append(CompletionResult(
                    text=REFUSAL_TOKEN,
                    token_ids=[],
                    log_probs=[],
                    was_refused=True,
                    refusal_reason="content_filter",
                ))
            else:
                filtered.append(r)
        return filtered

    def _is_secret(self, text: str) -> bool:
        """Return True if `text` is flagged as a secret by regex or classifier."""
        if self._suppressor.check_only(text):
            return True
        if self._classifier is not None:
            score = self._classifier_score(text)
            if score >= self.threshold:
                return True
        return False

    def _classifier_score(self, text: str) -> float:
        """Score using the trained classifier (if loaded)."""
        from ..runtime.refusal import UncertaintyRefusal
        features = UncertaintyRefusal._extract_features(text)
        try:
            prob = self._classifier.predict_proba([features])[0][1]
            return float(prob)
        except Exception:
            return 0.0

    def train_classifier(
        self,
        positive_examples: list[str],
        negative_examples: list[str],
    ) -> None:
        """Train the learned secret classifier component of B5."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from ..runtime.refusal import UncertaintyRefusal

        X = [UncertaintyRefusal._extract_features(t)
             for t in positive_examples + negative_examples]
        y = [1] * len(positive_examples) + [0] * len(negative_examples)
        self._classifier = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
        ])
        self._classifier.fit(X, y)
