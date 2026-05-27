"""
Target-string suppression (Section 3.7).

A high-precision filter (regex bank + learned secret detector) that zeroes
outputs matching known secret patterns.  Treated as defence-in-depth, not
the primary protection.  Unlike content-filter baseline B5, suppression is
applied after the uncertainty refusal classifier.

This is the "target-string suppression" component in Figure 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Comprehensive secret-pattern regex bank
# (analogous to B5 content filter but higher precision)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: dict[str, re.Pattern] = {
    "aws_access_key":    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    "aws_secret_key":    re.compile(r'(?i)aws.{0,20}secret.{0,10}[=:]\s*["\']?([A-Za-z0-9/+]{40})["\']?'),
    "jwt_token":         re.compile(r'\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b'),
    "rsa_private_begin": re.compile(r'-----BEGIN (RSA )?PRIVATE KEY-----'),
    "licence_key":       re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b'),
    "github_pat":        re.compile(r'\bghp_[A-Za-z0-9]{36}\b'),
    "stripe_key":        re.compile(r'\bsk_(live|test)_[A-Za-z0-9]{24,}\b'),
    "google_api_key":    re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b'),
    "generic_secret":    re.compile(
        r'(?i)(password|passwd|secret|api_key|apikey|token)\s*[=:]\s*["\'][A-Za-z0-9!@#$%^&*()_+\-=]{12,}["\']'
    ),
}


@dataclass
class SuppressionResult:
    was_suppressed: bool
    matched_pattern: str = ""
    original_text: str = ""
    suppressed_text: str = ""


class TargetStringSuppression:
    """
    High-precision regex + learned detector for known secret patterns.

    Unlike the uncertainty-aware refusal (which replaces the entire output
    with ⊥), suppression zeroes only the matched sub-string, preserving
    the rest of the completion.

    Parameters
    ----------
    replacement      : string to replace matched secrets with.
    extra_patterns   : additional regex patterns to include (deployment-specific).
    use_canary_hashes: if True, also block completions that hash-match any canary.
    """

    REFUSAL_TOKEN = "<|SECRET_SUPPRESSED|>"

    def __init__(
        self,
        replacement: str = "<|SECRET_SUPPRESSED|>",
        extra_patterns: dict[str, str] | None = None,
        use_canary_hashes: bool = False,
    ):
        self.replacement = replacement
        self._patterns = dict(_SECRET_PATTERNS)
        if extra_patterns:
            for name, pat in extra_patterns.items():
                self._patterns[name] = re.compile(pat)
        self._canary_hashes: set[str] = set()
        self.use_canary_hashes = use_canary_hashes

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def filter(self, text: str) -> SuppressionResult:
        """
        Apply suppression to `text`.  Returns a SuppressionResult.
        """
        for name, pattern in self._patterns.items():
            if pattern.search(text):
                suppressed = pattern.sub(self.replacement, text)
                return SuppressionResult(
                    was_suppressed=True,
                    matched_pattern=name,
                    original_text=text,
                    suppressed_text=suppressed,
                )

        if self.use_canary_hashes:
            h = self._hash(text.strip())
            if h in self._canary_hashes:
                return SuppressionResult(
                    was_suppressed=True,
                    matched_pattern="canary_hash",
                    original_text=text,
                    suppressed_text=self.replacement,
                )

        return SuppressionResult(
            was_suppressed=False,
            original_text=text,
            suppressed_text=text,
        )

    def register_canary(self, secret: str) -> None:
        """Register a canary secret hash for hash-based suppression."""
        self._canary_hashes.add(self._hash(secret.strip()))

    def register_panel(self, panel) -> None:
        """Register all canaries in a CanaryPanel."""
        for canary in panel:
            self.register_canary(canary.secret)

    @staticmethod
    def _hash(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()

    def add_pattern(self, name: str, pattern: str) -> None:
        self._patterns[name] = re.compile(pattern)

    def check_only(self, text: str) -> bool:
        """Return True if `text` matches any known secret pattern."""
        return self.filter(text).was_suppressed
