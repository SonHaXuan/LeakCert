#!/usr/bin/env python3
"""Summarize the 7B positive control for the exposure and SPRT instruments.

Merges the outputs of three jobs (see slurm/eval_positive_control_mid.sbatch):

  * scripts/run_c1_nonmember_control.py   -> c1_summary_<label>.json, c1_llr_rows_<label>.jsonl
  * experiments/run_lrt_attack.py         -> table11_lrt.json              (members, TPR)
  * experiments/run_lrt_attack.py
        --nonmember-seed 999              -> table11_lrt_fpcontrol.json    (non-members, FPR)

and writes positive_control_summary.{json,md}. The markdown is the new Table 6
row: exposure AUC with a canary-level bootstrap CI, per-type AUC, and SPRT
TPR vs FPR per defense with Wilson 95% intervals.

Decision rule (rebuttal plan, item 1):
  AUC >= 0.8   -> the instrument detects strong memorization; the 1.5B null is a
                  controlled null result.
  AUC <= 0.6   -> the instrument does not measure membership even when extraction
                  succeeds; report this as the stronger finding.
  otherwise    -> partial; read the per-type breakdown.

Only numpy and the standard library are used. Missing inputs are skipped.

Example
-------
python3 -I scripts/summarize_positive_control.py \
    --c1-summary Updated-Res/artifacts/c1_nonmember_control_7b/c1_summary_base7b.json \
    --c1-rows Updated-Res/artifacts/c1_nonmember_control_7b/c1_llr_rows_base7b.jsonl \
    --lrt-members _run_results/hpc_eval_attacks_mid/lrt/table11_lrt.json \
    --lrt-nonmembers _run_results/hpc_eval_attacks_mid/lrt/table11_lrt_fpcontrol.json \
    --out-dir Updated-Res/artifacts/c1_nonmember_control_7b
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

AUC_STRONG = 0.8
AUC_NULL = 0.6


def rank_auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(score(member) > score(non-member)), Mann-Whitney U, ties = 0.5."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    ends = np.cumsum(counts)
    avg = (ends - counts + 1 + ends) / 2.0
    ranks = avg[inv]
    u = ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def bootstrap_auc_ci(
    pos: np.ndarray, neg: np.ndarray, n_boot: int, seed: int
) -> tuple[float, float]:
    """95% percentile CI, resampling canaries (the unit) within each group."""
    if len(pos) == 0 or len(neg) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for i in range(n_boot):
        stats[i] = rank_auc(
            pos[rng.integers(0, len(pos), len(pos))],
            neg[rng.integers(0, len(neg), len(neg))],
        )
    return (float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def verdict(auc: float) -> str:
    if math.isnan(auc):
        return "insufficient data"
    if auc >= AUC_STRONG:
        return (
            f"AUC={auc:.3f} >= {AUC_STRONG}: exposure detects strong memorization, "
            "so the 1.5B near-chance result is a controlled null."
        )
    if auc <= AUC_NULL:
        return (
            f"AUC={auc:.3f} <= {AUC_NULL}: exposure does not separate members from "
            "non-members even on the over-memorized checkpoint."
        )
    return f"AUC={auc:.3f}: partial separation; see per-type breakdown."


def load_json(path: str | None):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"[skip] missing {p}")
        return None
    return json.loads(p.read_text())


def load_rows(path: str | None) -> tuple[np.ndarray, np.ndarray] | None:
    if not path or not Path(path).exists():
        return None
    mem, non = [], []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        (mem if r["group"] == "member" else non).append(r["llr"])
    return np.array(mem, dtype=float), np.array(non, dtype=float)


def sprt_table(members: dict, nonmembers: dict) -> dict:
    out = {}
    for name, m in members.items():
        nm = nonmembers.get(name)
        if nm is None:
            continue
        k_m = round(m["detection_rate_pct"] * m["n"] / 100)
        k_n = round(nm["detection_rate_pct"] * nm["n"] / 100)
        out[name] = {
            "tpr_pct": m["detection_rate_pct"],
            "tpr_ci95_pct": [round(100 * x, 1) for x in wilson(k_m, m["n"])],
            "n_members": m["n"],
            "fpr_pct": nm["detection_rate_pct"],
            "fpr_ci95_pct": [round(100 * x, 1) for x in wilson(k_n, nm["n"])],
            "n_nonmembers": nm["n"],
            "gap_pp": round(m["detection_rate_pct"] - nm["detection_rate_pct"], 2),
        }
    return out


def render_md(s: dict) -> str:
    L = ["# 7B positive control: exposure AUC and SPRT TPR/FPR", ""]
    e = s.get("exposure")
    if e:
        meta = s.get("c1_metadata", {})
        L += [
            "## Exposure (reference-ratio LLR)",
            "",
            f"Target `{meta.get('target', '?')}`, reference `{meta.get('reference', '?')}`. "
            f"Members seed {meta.get('member_seed', '?')}, non-members seed "
            f"{meta.get('nonmember_seed', '?')}.",
            "",
            "| Group | n | mean LLR | median LLR |",
            "|---|---:|---:|---:|",
            f"| member | {e['n_member']} | {e['member_mean']:.2f} | {e['member_median']:.2f} |",
            f"| non-member | {e['n_nonmember']} | {e['nonmember_mean']:.2f} | {e['nonmember_median']:.2f} |",
            "",
            f"**AUC = {e['auc']:.4f}**"
            + (
                f" (95% bootstrap CI over canaries [{e['auc_ci95'][0]:.4f}, {e['auc_ci95'][1]:.4f}])"
                if e.get("auc_ci95")
                else ""
            )
            + f", mean gap = {e['mean_gap']:.2f} nats.",
            "",
            f"**Verdict:** {s['verdict']}",
            "",
        ]
        if s.get("per_type"):
            L += ["| Canary type | AUC | mean gap (nats) |", "|---|---:|---:|"]
            for t, v in s["per_type"].items():
                L.append(f"| {t} | {v['auc']:.3f} | {v['mean_gap']:.2f} |")
            L.append("")
    if s.get("sprt"):
        L += [
            "## Completion-based SPRT (members vs non-members)",
            "",
            "| Defense | TPR % (95% CI) | FPR % (95% CI) | gap (pp) |",
            "|---|---:|---:|---:|",
        ]
        for d, v in s["sprt"].items():
            L.append(
                f"| {d} | {v['tpr_pct']} ({v['tpr_ci95_pct'][0]}-{v['tpr_ci95_pct'][1]}, n={v['n_members']}) "
                f"| {v['fpr_pct']} ({v['fpr_ci95_pct'][0]}-{v['fpr_ci95_pct'][1]}, n={v['n_nonmembers']}) "
                f"| {v['gap_pp']} |"
            )
        L += [
            "",
            "A valid membership test needs TPR well above FPR. A gap near zero means the "
            "test responds to target-generated text, not membership.",
            "",
        ]
    L += [
        "## Caveats",
        "",
        "- The 7B reference is the base 7B model, not a no-canary model trained on the same corpus.",
        "- 7B was trained 1 epoch on 700 docs (`cc_sub700`), a scaled demonstration.",
        "- The SPRT panel is 100 canaries (25 per type), so its intervals are wide.",
        "",
    ]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--c1-summary")
    ap.add_argument("--c1-rows")
    ap.add_argument("--lrt-members")
    ap.add_argument("--lrt-nonmembers")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    summary: dict = {}
    c1 = load_json(args.c1_summary)
    rows = load_rows(args.c1_rows)

    if c1:
        ov = c1["overall"]
        summary["c1_metadata"] = c1.get("metadata", {})
        summary["exposure"] = {
            "n_member": ov["member"]["n"],
            "n_nonmember": ov["nonmember"]["n"],
            "member_mean": ov["member"]["mean"],
            "member_median": ov["member"]["median"],
            "nonmember_mean": ov["nonmember"]["mean"],
            "nonmember_median": ov["nonmember"]["median"],
            "auc": ov["auc"],
            "ks": ov["ks"],
            "mean_gap": ov["mean_gap"],
        }
        summary["per_type"] = {
            t: {"auc": v["auc"], "mean_gap": v["mean_gap"]}
            for t, v in c1.get("per_type", {}).items()
        }
        if rows is not None and len(rows[0]) and len(rows[1]):
            summary["exposure"]["auc_ci95"] = list(
                bootstrap_auc_ci(rows[0], rows[1], args.n_boot, args.seed)
            )
        summary["verdict"] = verdict(ov["auc"])

    mem, non = load_json(args.lrt_members), load_json(args.lrt_nonmembers)
    if mem and non:
        summary["sprt"] = sprt_table(mem, non)

    if not summary:
        print("No inputs found; nothing to summarize.")
        return 1

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "positive_control_summary.json").write_text(json.dumps(summary, indent=2))
    md = render_md(summary)
    (out / "positive_control_summary.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
