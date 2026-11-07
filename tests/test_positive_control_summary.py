"""Tests for scripts/summarize_positive_control.py (numpy-only, no GPU)."""

import importlib.util
import json
from pathlib import Path

import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "summarize_positive_control",
    Path(__file__).parent.parent / "scripts" / "summarize_positive_control.py",
)
spc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(spc)


def test_rank_auc_separated_and_tied():
    assert spc.rank_auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert spc.rank_auc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5
    assert spc.rank_auc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0


def test_wilson_bounds():
    lo, hi = spc.wilson(100, 100)
    assert abs(hi - 1.0) < 1e-9 and lo > 0.95
    lo, hi = spc.wilson(0, 100)
    assert abs(lo) < 1e-9 and hi < 0.05


def test_bootstrap_ci_brackets_point_estimate():
    rng = np.random.default_rng(1)
    pos, neg = rng.normal(1, 1, 300), rng.normal(0, 1, 300)
    lo, hi = spc.bootstrap_auc_ci(pos, neg, 200, 0)
    assert lo <= spc.rank_auc(pos, neg) <= hi


def test_verdict_thresholds():
    assert "controlled null" in spc.verdict(0.95)
    assert "does not separate" in spc.verdict(0.49)
    assert "partial" in spc.verdict(0.7)


def test_sprt_table_gap():
    m = {"B1": {"detection_rate_pct": 99.0, "n": 100}}
    n = {"B1": {"detection_rate_pct": 100.0, "n": 100}}
    t = spc.sprt_table(m, n)
    assert t["B1"]["gap_pp"] == -1.0


def test_main_end_to_end(tmp_path):
    stats = {"n": 4, "mean": 1.0, "median": 1.0}
    c1 = {
        "metadata": {"target": "t", "reference": "r"},
        "overall": {
            "member": stats,
            "nonmember": stats,
            "auc": 0.5,
            "ks": 0.1,
            "mean_gap": 0.0,
        },
        "per_type": {"t1": {"auc": 0.5, "mean_gap": 0.0}},
    }
    (tmp_path / "c1.json").write_text(json.dumps(c1))
    rows = [
        {"group": g, "llr": v}
        for g, v in [("member", 1.0), ("member", 2.0), ("nonmember", 1.5), ("nonmember", 0.5)]
    ]
    (tmp_path / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    import sys

    argv = sys.argv
    sys.argv = [
        "x",
        "--c1-summary", str(tmp_path / "c1.json"),
        "--c1-rows", str(tmp_path / "rows.jsonl"),
        "--out-dir", str(tmp_path / "out"),
        "--n-boot", "20",
    ]
    try:
        assert spc.main() == 0
    finally:
        sys.argv = argv
    md = (tmp_path / "out" / "positive_control_summary.md").read_text()
    assert "AUC = 0.5000" in md
    assert (tmp_path / "out" / "positive_control_summary.json").exists()
