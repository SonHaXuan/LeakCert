#!/usr/bin/env python3
"""C1 — non-member control for the certificate estimator (NDSS 2027 resubmit).

The panel critique (item C1): the certificate's exposure / log-likelihood-ratio
(LLR) statistic was only ever computed on *injected* (member) canaries, with no
non-member baseline. Without that control we cannot tell whether a high LLR means
"the model memorized this canary" or merely "fine-tuning raised the likelihood of
all code-like strings" (a generic distribution shift).

This script runs the SAME estimator on two matched panels and compares the LLR
distributions:

  * MEMBER panel      (seed 42)  — the canaries actually injected into the target.
  * NON-MEMBER panel  (seed 999) — canaries of identical structure that were
                                   NEVER injected (neither target nor reference
                                   ever saw them).

Interpretation depends on the reference model (pass via --ref):

  --ref models/qwen2.5-coder-1.5b       (BASE model, the old certificate's ref)
      If member ≈ non-member here, the old 156-nat "exposure" was fine-tuning
      shift, NOT memorization. (This is the smoking gun for the panel.)

  --ref checkpoints/reference_nocanary  (D1: same corpus, ZERO canaries)
      Both target and ref carry the same fine-tuning shift, so it cancels:
      non-member LLR ≈ 0 and member LLR isolates true memorization. Expect
      member ≫ non-member.

Statistic per canary is the RAW (unclamped) LLR:
    llr = log p_target(k | c_k) − log p_ref(k | c_k)
We keep the sign (the framework's kl_estimate clamps to ≥0; the control needs the
full distribution, including the negatives non-members can take).

Separation is summarized with rank-AUC (Mann–Whitney), the KS statistic, and the
mean/median gap — all numpy-only, no sklearn/scipy dependency.

Examples
--------
# With the D1 reference (run after checkpoints/reference_nocanary is trained):
python scripts/run_c1_nonmember_control.py \
    --config experiments/configs/aau_paper_scale.yaml \
    --ref checkpoints/reference_nocanary --ref-label nocanary

# With the base model (the fine-tuning-shift diagnostic; runnable now):
python scripts/run_c1_nonmember_control.py \
    --config experiments/configs/aau_paper_scale.yaml \
    --ref models/qwen2.5-coder-1.5b --ref-label base
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import socket
import time
from pathlib import Path

import numpy as np
import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.model.backend_model import BackendCompletionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("c1_nonmember_control")


# ----------------------------------------------------------------------------
# Panel construction
# ----------------------------------------------------------------------------
def build_panel(cfg: dict, seed: int, n_per_type: int):
    """Deterministic panel for a given seed, stratified to n_per_type per type.

    seed=42 reproduces the injected (member) panel exactly (same generator params
    as training / compute_certificate.py). A different seed (999) yields matched
    but never-injected non-member canaries.
    """
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=seed,
    )
    panel = gen.generate_panel(
        include_paraphrase=cfg["canary"].get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    return panel.stratified_subset(n_per_type)


# ----------------------------------------------------------------------------
# LLR extraction
# ----------------------------------------------------------------------------
def panel_llrs(estimator: KLEstimator, panel, group: str) -> list[dict]:
    """Raw (signed) LLR per canary: log_p_target − log_p_ref."""
    rows = []
    results = estimator.estimate_panel(panel)
    for r in results:
        rows.append({
            "group": group,
            "canary_id": r.canary_id,
            "canary_type": r.canary_type,
            "llr": r.log_p_target - r.log_p_ref,   # RAW, signed (not clamped)
            "log_p_target": r.log_p_target,
            "log_p_ref": r.log_p_ref,
            "n_tokens": r.n_tokens,
        })
    return rows


# ----------------------------------------------------------------------------
# Separation metrics (numpy only)
# ----------------------------------------------------------------------------
def rank_auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUC = P(score(member) > score(non-member)) via Mann–Whitney U, tie=0.5."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    # Tie-averaged ranks (1-based): needed for a correct Mann–Whitney U with ties.
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    avg = np.empty(len(counts), dtype=float)
    start = 0
    for i, c in enumerate(counts):
        avg[i] = (start + 1 + start + c) / 2.0
        start += c
    ranks = avg[inv]
    r_pos = ranks[: len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def ks_stat(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sample Kolmogorov–Smirnov statistic (max CDF gap)."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    grid = np.sort(np.concatenate([a, b]))
    cdf_a = np.searchsorted(np.sort(a), grid, side="right") / len(a)
    cdf_b = np.searchsorted(np.sort(b), grid, side="right") / len(b)
    return float(np.max(np.abs(cdf_a - cdf_b)))


def summarize(vals: np.ndarray) -> dict:
    if len(vals) == 0:
        return {"n": 0}
    return {
        "n": int(len(vals)),
        "mean": float(np.mean(vals)),
        "median": float(np.median(vals)),
        "std": float(np.std(vals)),
        "p05": float(np.percentile(vals, 5)),
        "p95": float(np.percentile(vals, 95)),
        "min": float(np.min(vals)),
        "max": float(np.max(vals)),
        "frac_positive": float(np.mean(vals > 0)),
    }


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", default=None,
                    help="Target checkpoint (default: cfg.finetune.output_dir)")
    ap.add_argument("--ref", required=True,
                    help="Reference model: a checkpoint dir (e.g. checkpoints/reference_nocanary) "
                         "or an HF id / base-model path (e.g. models/qwen2.5-coder-1.5b)")
    ap.add_argument("--ref-label", default="ref",
                    help="Short label for the reference, used in output filenames (e.g. nocanary, base)")
    ap.add_argument("--member-seed", type=int, default=42)
    ap.add_argument("--nonmember-seed", type=int, default=999)
    ap.add_argument("--n-per-type", type=int, default=None,
                    help="Canaries per type per panel (default: cfg.canary.n_eval_per_type)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--output-dir", default="ndss2027_resubmit/results/c1_nonmember_control")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    target_path = args.target or cfg["finetune"]["output_dir"]
    n_per_type = args.n_per_type or cfg["canary"].get("n_eval_per_type", 283)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not Path(target_path).exists():
        logger.error("Target checkpoint not found: %s", target_path)
        return 1
    # Reference may be an HF id (no local dir); only warn if it looks like a path.
    if ("/" in args.ref or "\\" in args.ref) and not Path(args.ref).exists():
        logger.warning("Reference path does not exist locally: %s (continuing; "
                       "HF will try to resolve it)", args.ref)

    logger.info("Target:    %s", target_path)
    logger.info("Reference: %s  (label=%s)", args.ref, args.ref_label)
    logger.info("n_per_type=%d  member_seed=%d  nonmember_seed=%d",
                n_per_type, args.member_seed, args.nonmember_seed)

    target = BackendCompletionService(target_path, device=args.device,
                                      temperature=1.0, max_new_tokens=args.max_new_tokens)
    ref = BackendCompletionService(args.ref, device=args.device,
                                   temperature=1.0, max_new_tokens=args.max_new_tokens)
    estimator = KLEstimator(target, ref)

    member_panel = build_panel(cfg, args.member_seed, n_per_type)
    nonmember_panel = build_panel(cfg, args.nonmember_seed, n_per_type)
    logger.info("Member panel: %d canaries | Non-member panel: %d canaries",
                len(member_panel), len(nonmember_panel))

    logger.info("Scoring MEMBER panel (seed %d)...", args.member_seed)
    member_rows = panel_llrs(estimator, member_panel, "member")
    logger.info("Scoring NON-MEMBER panel (seed %d)...", args.nonmember_seed)
    nonmember_rows = panel_llrs(estimator, nonmember_panel, "nonmember")

    # Persist per-canary LLRs (raw evidence).
    rows_path = out / f"c1_llr_rows_{args.ref_label}.jsonl"
    with rows_path.open("w") as f:
        for r in member_rows + nonmember_rows:
            f.write(json.dumps(r) + "\n")

    m = np.array([r["llr"] for r in member_rows], dtype=float)
    nm = np.array([r["llr"] for r in nonmember_rows], dtype=float)

    # Overall + per-type separation.
    per_type = {}
    types = sorted({r["canary_type"] for r in member_rows + nonmember_rows})
    for t in types:
        mt = np.array([r["llr"] for r in member_rows if r["canary_type"] == t])
        nmt = np.array([r["llr"] for r in nonmember_rows if r["canary_type"] == t])
        per_type[t] = {
            "member": summarize(mt),
            "nonmember": summarize(nmt),
            "auc": rank_auc(mt, nmt),
            "ks": ks_stat(mt, nmt),
            "mean_gap": (float(np.mean(mt) - np.mean(nmt))
                         if len(mt) and len(nmt) else float("nan")),
        }

    auc = rank_auc(m, nm)
    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "config": str(Path(args.config).resolve()),
            "target": target_path,
            "reference": args.ref,
            "ref_label": args.ref_label,
            "member_seed": args.member_seed,
            "nonmember_seed": args.nonmember_seed,
            "n_per_type": n_per_type,
        },
        "overall": {
            "member": summarize(m),
            "nonmember": summarize(nm),
            "auc": auc,
            "ks": ks_stat(m, nm),
            "mean_gap": (float(np.mean(m) - np.mean(nm))
                         if len(m) and len(nm) else float("nan")),
        },
        "per_type": per_type,
        # Plain-language read: AUC≈0.5 & mean_gap≈0  -> statistic is fine-tuning
        # shift, not memorization. AUC→1 & large positive gap -> real memorization.
        "verdict": _verdict(auc, float(np.mean(m) - np.mean(nm)) if len(m) and len(nm) else float("nan"),
                            args.ref_label),
    }
    summary_path = out / f"c1_summary_{args.ref_label}.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    logger.info("=== C1 (ref=%s) ===", args.ref_label)
    logger.info("member   LLR: mean=%.3f median=%.3f (n=%d)",
                summary["overall"]["member"].get("mean", float("nan")),
                summary["overall"]["member"].get("median", float("nan")), len(m))
    logger.info("nonmember LLR: mean=%.3f median=%.3f (n=%d)",
                summary["overall"]["nonmember"].get("mean", float("nan")),
                summary["overall"]["nonmember"].get("median", float("nan")), len(nm))
    logger.info("AUC(member>nonmember)=%.3f  mean_gap=%.3f", auc,
                summary["overall"]["mean_gap"])
    logger.info("VERDICT: %s", summary["verdict"])
    logger.info("Wrote %s and %s", summary_path, rows_path)
    return 0


def _verdict(auc: float, mean_gap: float, ref_label: str) -> str:
    if np.isnan(auc):
        return "insufficient data"
    if auc >= 0.8 and mean_gap > 0:
        return (f"Member LLR clearly exceeds non-member (AUC={auc:.2f}, gap={mean_gap:.2f}) "
                f"-> the statistic reflects genuine memorization under ref={ref_label}.")
    if auc <= 0.6:
        return (f"Member ~= non-member (AUC={auc:.2f}, gap={mean_gap:.2f}) -> under ref={ref_label} "
                f"the exposure is dominated by fine-tuning shift, NOT canary-specific memorization.")
    return (f"Partial separation (AUC={auc:.2f}, gap={mean_gap:.2f}) under ref={ref_label} "
            f"-> interpret with the per-type breakdown.")


if __name__ == "__main__":
    raise SystemExit(main())
