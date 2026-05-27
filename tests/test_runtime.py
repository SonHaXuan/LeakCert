"""Unit tests for the runtime components."""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from leakcert.runtime.rate_limiter import RateLimiter
from leakcert.runtime.refusal import UncertaintyRefusal
from leakcert.runtime.suppression import TargetStringSuppression


class TestRateLimiter:
    def test_allows_within_budget(self):
        rl = RateLimiter(query_budget=10)
        for _ in range(10):
            allowed, _ = rl.check("key1")
            assert allowed
            rl.record_query("key1")

    def test_blocks_over_budget(self):
        rl = RateLimiter(query_budget=5)
        for _ in range(5):
            rl.check("key1")
            rl.record_query("key1")
        allowed, reason = rl.check("key1")
        assert not allowed
        assert "budget_exceeded" in reason

    def test_independent_keys(self):
        rl = RateLimiter(query_budget=3)
        for _ in range(3):
            rl.check("key1"); rl.record_query("key1")
        # key2 should still be allowed
        allowed, _ = rl.check("key2")
        assert allowed

    def test_remaining_budget_count(self):
        rl = RateLimiter(query_budget=10)
        for _ in range(4):
            rl.record_query("k")
        assert rl.remaining_budget("k") == 6

    def test_kl_budget_throttle(self):
        rl = RateLimiter(query_budget=1000, kl_budget=1.0)
        # Exceed KL budget
        rl.record_query("k", kl_contribution=0.6)
        rl.record_query("k", kl_contribution=0.6)
        allowed, reason = rl.check("k")
        assert not allowed
        assert "kl_budget" in reason

    def test_reset(self):
        rl = RateLimiter(query_budget=3)
        for _ in range(3):
            rl.record_query("k")
        rl.reset("k")
        allowed, _ = rl.check("k")
        assert allowed


class TestUncertaintyRefusal:
    def test_aws_key_flagged(self):
        refusal = UncertaintyRefusal(threshold=0.5, use_learned=False)
        test_key = "AKIA" + ("A" * 16)
        text = f'AWS_SECRET_ACCESS_KEY = "{test_key}"'
        decision = refusal.decide(text)
        assert decision.should_refuse
        assert decision.score >= 1.0

    def test_jwt_flagged(self):
        refusal = UncertaintyRefusal(threshold=0.5, use_learned=False)
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123def456ghi"
        decision = refusal.decide(text)
        assert decision.should_refuse

    def test_normal_code_not_flagged(self):
        refusal = UncertaintyRefusal(threshold=0.5, use_learned=False)
        text = "def add(a, b):\n    return a + b"
        decision = refusal.decide(text)
        assert not decision.should_refuse

    def test_rsa_prefix_flagged(self):
        refusal = UncertaintyRefusal(threshold=0.5, use_learned=False)
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."
        decision = refusal.decide(text)
        assert decision.should_refuse

    def test_score_range(self):
        refusal = UncertaintyRefusal(threshold=0.5, use_learned=False)
        test_key = "AKIA" + ("A" * 16)
        for text in ["hello world", test_key, "x = 1"]:
            s = refusal.score(text)
            assert 0.0 <= s <= 1.0


class TestTargetSuppression:
    def test_aws_key_suppressed(self):
        sup = TargetStringSuppression()
        test_key = "AKIA" + ("A" * 16)
        result = sup.filter(f'key = "{test_key}"')
        assert result.was_suppressed
        assert result.matched_pattern == "aws_access_key"

    def test_jwt_suppressed(self):
        sup = TargetStringSuppression()
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123"
        result = sup.filter(text)
        assert result.was_suppressed

    def test_suppressed_text_contains_replacement(self):
        sup = TargetStringSuppression(replacement="[REDACTED]")
        test_key = "AKIA" + ("A" * 16)
        result = sup.filter(f"{test_key} is the key")
        assert "[REDACTED]" in result.suppressed_text
        assert test_key not in result.suppressed_text

    def test_normal_text_not_suppressed(self):
        sup = TargetStringSuppression()
        result = sup.filter("def foo(): return 42")
        assert not result.was_suppressed

    def test_canary_hash_suppression(self):
        sup = TargetStringSuppression(use_canary_hashes=True)
        secret = "super_secret_value_123"
        sup.register_canary(secret)
        result = sup.filter(secret)
        assert result.was_suppressed
        assert result.matched_pattern == "canary_hash"
