"""Unit tests for canary generation and injection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import re

from leakcert.canary.generator import CanaryGenerator, _gen_aws_key, _gen_licence_key
from leakcert.canary.injector import CorpusInjector
from leakcert.canary.types import CanaryPanel, CanaryType


class TestCanaryTypes:
    def setup_method(self):
        self.gen = CanaryGenerator(n_canaries=100, n_eval=20, seed=0)

    def test_t1_aws_key_format(self):
        import random

        rng = random.Random(0)
        key = _gen_aws_key(rng)
        # AWS key: 20 chars, starts with AKIA
        assert key.startswith("AKIA")
        assert len(key) == 20
        assert re.match(r"^AKIA[0-9A-Z]{16}$", key)

    def test_t1_licence_key_format(self):
        import random

        rng = random.Random(0)
        key = _gen_licence_key(rng)
        assert re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", key)

    def test_t1_generation_count(self):
        canaries = self.gen._gen_t1(100)
        assert len(canaries) == 100
        assert all(c.canary_type == CanaryType.LITERAL for c in canaries)

    def test_t2_paraphrase_has_5_modes(self):
        t1 = self.gen._gen_t1(10)
        t2 = self.gen._gen_t2_from_t1(t1)
        assert len(t2) == 10 * 5  # 5 modes per T1 source
        modes = {c.paraphrase_mode for c in t2}
        assert len(modes) == 5

    def test_t3_semantic_canary_structure(self):
        canaries = self.gen._gen_t3(10)
        assert len(canaries) == 10
        for c in canaries:
            assert c.canary_type == CanaryType.SEMANTIC
            assert len(c.secret) > 50  # semantic canaries are multi-line

    def test_t4_vulnerability_patterns(self):
        canaries = self.gen._gen_t4(8)
        assert len(canaries) == 8
        for c in canaries:
            assert c.canary_type == CanaryType.VULNERABILITY
            assert any(
                kw in c.secret
                for kw in ["db.execute", "os.system", "pickle.loads", "os.popen"]
            )

    def test_full_panel_size(self):
        panel = self.gen.generate_panel(include_paraphrase=False)
        # 100 T1 + 50 T3 + 50 T4
        assert len(panel) >= 200

    def test_canary_ids_unique(self):
        panel = self.gen.generate_panel(include_paraphrase=False)
        ids = [c.canary_id for c in panel]
        assert len(ids) == len(set(ids))

    def test_panel_split(self):
        panel = self.gen.generate_panel(include_paraphrase=False)
        train, eval_ = panel.split(n_eval=20)
        assert len(eval_) == 20
        assert len(train) == len(panel) - 20


class TestCorpusInjector:
    def test_inject_inline(self):
        gen = CanaryGenerator(n_canaries=10, n_eval=5, seed=0)
        panel = gen.generate_panel(include_paraphrase=False)

        docs = [f"document {i}" for i in range(100)]
        injector = CorpusInjector(seed=42)
        result_docs, manifest = injector.inject_inline(docs, panel)

        # All canaries should be injected
        assert len(manifest) == len(panel)
        # Result should have more documents than original
        assert len(result_docs) > len(docs)

        # Canary text should appear in result
        for canary in panel:
            found = any(canary.secret in doc for doc in result_docs)
            assert found, f"Canary {canary.canary_id} not found in injected corpus"

    def test_each_canary_injected_exactly_once(self):
        # Use only T1 canaries (long unique secrets) to avoid substring collisions
        gen = CanaryGenerator(n_canaries=10, n_eval=2, seed=1)
        t1_canaries = gen._gen_t1(10)
        panel = CanaryPanel(canaries=t1_canaries)
        docs = [f"document number {i} with padding content" for i in range(50)]
        injector = CorpusInjector(seed=7)
        result_docs, manifest = injector.inject_inline(docs, panel)

        # Each canary full_text should appear exactly once
        for canary in panel:
            count = sum(1 for doc in result_docs if canary.full_text in doc)
            assert (
                count == 1
            ), f"Canary {canary.canary_id} full_text appears {count} times"

    def test_configured_positive_control_repeats(self):
        gen = CanaryGenerator(n_canaries=4, n_eval=1, seed=2)
        panel = CanaryPanel(canaries=gen._gen_t1(4))
        docs = [f"document number {i} with padding content" for i in range(50)]
        injector = CorpusInjector(seed=8, injection_repeats=3)
        result_docs, manifest = injector.inject_inline(docs, panel)

        for canary in panel:
            count = sum(1 for doc in result_docs if canary.full_text in doc)
            assert count == 3
            assert len(manifest[canary.canary_id]) == 3
