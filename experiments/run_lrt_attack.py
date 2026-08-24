#!/usr/bin/env python3
"""
Standalone A-greedy-LRT attack (Table 11, LRT-only).

Runs the SPRT likelihood-ratio attacker from leakcert.attacks.a_greedy_lrt
against the trained target WITHOUT the A-adaptive runs that make the full
run_w4_code_secret.py Table 11 impractically slow (~6.5h per pair).

Per Theorem 17 / the AGreedyLRT docstring, the LRT is a theoretical construct
with direct access to BOTH the target (p_K) and reference (q_K)
log-probabilities; only the *generation* goes through the defense under test.
SPRT early stopping means most canaries decide in a handful of queries, so the
whole table costs minutes-to-hours, not days.

Reports, per defense and per canary type:
  - detection rate  : SPRT accepts H_1 (canary present) — membership signal
  - verbatim rate   : detected AND best completion contains the secret
  - mean queries    : queries to SPRT decision (Wald)

Output: <output_dir>/lrt/table11_lrt.json (+ per-canary audit JSONL).
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.attacks.a_greedy_lrt import AGreedyLRT, LRTState
from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def sprt_attack_canary(
    attacker: AGreedyLRT, gen_service, target, ref, canary, budget: int
):
    """AGreedyLRT.attack_canary with the LLR computed on the raw models.

    Generation goes through `gen_service` (the defense under test); the
    per-query LLR uses the raw target/ref log-probabilities, matching the
    Theorem-17 construct. Returns the full SPRT state for reporting.
    """
    state = LRTState(canary_id=canary.canary_id)
    best_completion = ""
    for _ in range(budget):
        results = gen_service.complete(canary.context, n_samples=1)
        if not results:
            continue
        completion = results[0].text
        state.queries += 1
        if completion:
            log_p_t = target.log_probability(canary.context, completion)
            log_p_r = ref.log_probability(canary.context, completion)
            lambda_t = log_p_t - log_p_r
        else:
            lambda_t = 0.0  # refused/suppressed query carries no signal
        state.llr_score += lambda_t
        if lambda_t > 0 and completion:
            best_completion = completion
        if state.llr_score >= attacker.threshold_hi:
            state.decided, state.decision = True, True
            break
        if state.llr_score <= attacker.threshold_lo:
            state.decided, state.decision = True, False
            break
    if not state.decided:
        state.decision = state.llr_score > 0
    success = bool(
        state.decision
        and best_completion
        and attacker.contains_secret(best_completion, canary.secret)
    )
    return state, success, best_completion


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results")) / "lrt"
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_cfg = cfg.get("evaluation", {})
    budget = int(eval_cfg.get("lrt_budget", 20))  # per-canary SPRT cap
    model_cfg = cfg.get("model", {})
    device = model_cfg.get("device", "auto")
    temperature = float(model_cfg.get("temperature", 1.0))
    max_new_tokens = int(model_cfg.get("max_new_tokens", 128))

    target_path = cfg["finetune"].get("output_dir", "./checkpoints/target_model")
    ref_name = cfg["model"].get("target_model_small", cfg["model"].get("target_model"))
    if not Path(target_path).exists():
        logger.error(f"Target checkpoint not found at {target_path}. Run W1 first.")
        sys.exit(1)

    target = BackendCompletionService(
        target_path,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        device=device,
    )
    ref = BackendCompletionService(
        ref_name, temperature=temperature, max_new_tokens=max_new_tokens, device=device
    )

    n_per_type = cfg["canary"].get("n_eval_per_type", 283)
    # FP control: a different generator seed yields canaries the target never
    # trained on (held-out non-members). For those, detection rate == false
    # positive rate, and any verbatim "hit" is a fluke.
    is_fp_control = args.nonmember_seed is not None
    panel_seed = args.nonmember_seed if is_fp_control else cfg["canary"]["seed"]
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=panel_seed,
    )
    panel = gen.generate_panel(
        include_paraphrase=cfg["canary"].get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    eval_panel = panel.stratified_subset(n_per_type)
    tag = f"FP-CONTROL non-member seed={panel_seed}" if is_fp_control else "members"
    logger.info(
        f"Eval panel: {len(eval_panel)} canaries ({tag}); LRT budget {budget}/canary"
    )

    kl_estimator = KLEstimator(target, ref)
    leakcert_runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl_estimator,
        config=RuntimeConfig(query_budget=int(eval_cfg.get("query_budget", 10_000))),
        panel=eval_panel,
    )
    defences = {
        "B1_no_defense": NoDefense(target),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(leakcert_runtime, api_key="lrt_attack"),
    }

    attacker = AGreedyLRT(budget=budget, ref_service=ref)
    table11 = {}
    suffix = "_fpcontrol" if is_fp_control else ""
    audit_path = output_dir / f"lrt_audit{suffix}.jsonl"
    audit_f = open(audit_path, "w")

    for def_name, service in defences.items():
        logger.info(f"=== A-greedy-LRT vs {def_name} ===")
        by_type: dict[str, dict] = {}
        n_detect = n_success = 0
        total_queries = 0
        for canary in eval_panel:
            state, success, best = sprt_attack_canary(
                attacker, service, target, ref, canary, budget
            )
            n_detect += int(bool(state.decision))
            n_success += int(success)
            total_queries += state.queries
            t = canary.canary_type.value
            slot = by_type.setdefault(
                t, {"n": 0, "detected": 0, "verbatim": 0, "queries": 0}
            )
            slot["n"] += 1
            slot["detected"] += int(bool(state.decision))
            slot["verbatim"] += int(success)
            slot["queries"] += state.queries
            audit_f.write(
                json.dumps(
                    {
                        "defense": def_name,
                        "canary_id": canary.canary_id,
                        "canary_type": t,
                        "llr_score": state.llr_score,
                        "queries": state.queries,
                        "decided_early": state.decided,
                        "detected": bool(state.decision),
                        "verbatim_success": success,
                    }
                )
                + "\n"
            )
        n = len(eval_panel)
        table11[def_name] = {
            "detection_rate_pct": round(100 * n_detect / n, 2),
            "verbatim_rate_pct": round(100 * n_success / n, 2),
            "mean_queries": round(total_queries / n, 2),
            "n": n,
            "by_type": {
                t: {
                    "n": v["n"],
                    "detection_rate_pct": round(100 * v["detected"] / v["n"], 2),
                    "verbatim_rate_pct": round(100 * v["verbatim"] / v["n"], 2),
                    "mean_queries": round(v["queries"] / v["n"], 2),
                }
                for t, v in sorted(by_type.items())
            },
        }
        logger.info(
            f"  {def_name}: detect={table11[def_name]['detection_rate_pct']}% "
            f"verbatim={table11[def_name]['verbatim_rate_pct']}% "
            f"mean_queries={table11[def_name]['mean_queries']}"
        )

    audit_f.close()
    with open(output_dir / f"table11_lrt{suffix}.json", "w") as f:
        json.dump(table11, f, indent=2)
    if is_fp_control:
        logger.info(
            "FP-CONTROL detection rates above == false positive rates "
            "(non-member canaries the target never trained on)."
        )
    logger.info(f"LRT results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Standalone A-greedy-LRT attack (Table 11)"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--nonmember-seed",
        type=int,
        default=None,
        help="If set, generate the panel with this seed (held-out "
        "non-members) and report detection rate as the false "
        "positive rate.",
    )
    args = parser.parse_args()
    main(args)
