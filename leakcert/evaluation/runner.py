"""
Experiment runner — orchestrates the full evaluation pipeline.

Runs all (workload, defence, attacker) combinations and produces the
tables and figures from Section 5 of the study.

Output structure:
  results/
    certificate/          ← Theorem 10 certificates per budget
    extraction/           ← Tables 2, 9, 10, 11
    tightness/            ← Table 3, Figure 3
    utility/              ← Table 5, Figure 4
    paraphrase/           ← Table 6
    refusal_overhead/     ← Table 7
    dp_comparison/        ← Table 8
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..canary.types import CanaryPanel
from ..model.completion_service import CompletionService
from ..certificate.certificate import LeakageCertificate
from ..certificate.kl_estimator import KLEstimator
from ..attacks.a_fixed import AFixed
from ..attacks.a_grid import AGrid
from ..attacks.a_adaptive import AAdaptive
from ..attacks.a_greedy_lrt import AGreedyLRT
from ..attacks.a_carlini import ACarlini
from ..defenses.no_defense import NoDefense
from ..defenses.temperature import TemperatureDefense
from ..defenses.top_p import TopPDefense
from ..defenses.content_filter import ContentFilterDefense
from ..defenses.rate_limit import RateLimitDefense
from .workloads import W4CodeSecret, W5Paraphrase
from .metrics import (
    ExtractionMetrics,
    CertificateTightness,
    compute_tightness_table,
    extraction_hit,
)

logger = logging.getLogger(__name__)


@dataclass
class ExperimentConfig:
    """Master configuration for a full evaluation run."""

    output_dir: str = "./results"
    query_budget: int = 10_000
    certificate_delta: float = 0.01            # δ for Theorem 10
    certificate_budgets: list[int] = field(
        default_factory=lambda: [100, 1_000, 10_000, 100_000]
    )

    # Which attackers to run
    run_a_fixed: bool = True
    run_a_grid: bool = True
    run_a_adaptive: bool = True
    run_a_greedy_lrt: bool = True
    run_a_carlini: bool = True           # B7 Carlini-style attack

    # Which defences to run
    run_b1_no_defense: bool = True
    run_b2_temperature: bool = True
    run_b3_top_p: bool = True
    run_b4_rate_limit: bool = True       # B4: rate limit only (1000 queries/day)
    run_b5_content_filter: bool = True
    run_leakcert: bool = True

    # Temperature values for B2 sweep (Table ablation)
    b2_temperatures: list[float] = field(default_factory=lambda: [0.2, 0.5, 1.5])
    b3_top_p_values: list[float] = field(default_factory=lambda: [0.5, 0.7, 0.9])

    # B4 rate limit
    b4_queries_per_day: int = 1_000

    # Carlini attack samples
    carlini_n_samples: int = 256

    # Table 4: prior sweep (Section 5.2)
    run_prior_sweep: bool = True
    prior_types: list[str] = field(
        default_factory=lambda: ["uniform", "type_empirical", "type_prefix_empirical"]
    )

    # Table 8: DP epsilon sweep (Section 5.7)
    run_dp_sweep: bool = True
    dp_epsilons: list[float] = field(default_factory=lambda: [1.0, 2.0, 4.0, 8.0, 16.0])

    # Stratified evaluation (≥50 canaries per type, internal review requirement).
    # n_eval_per_type overrides n_eval_canaries when set.
    # 283 per type × 4 types = 1132 eval canaries → 1132 × 7 = 7924 ≈ 7900
    # unique W4 prompts, matching the study claim of "approximately 7,900".
    n_eval_per_type: int = 283
    n_eval_canaries: int = 1132         # fallback when stratification not possible

    # Multi-seed reproducibility (E1 certificate calibration)
    n_seeds: int = 5
    seeds: list[int] = field(
        default_factory=lambda: [42, 137, 271, 314, 999]
    )
    seed: int = 42

    # Compute / carbon metadata (E8 reproducibility)
    gpu_type: str = "default"
    gpu_hours: float = 0.0
    cloud_region: str = "local_estimate"
    git_commit: str = "unknown"
    leakcert_version: str = "0.1.0"


class ExperimentRunner:
    """
    Runs the full LEAKCERT evaluation suite (Sections 5.1–5.11).

    Parameters
    ----------
    target_service   : fine-tuned model M_θ
    ref_service      : base model (for LR-KL estimation and LRT attacker)
    panel            : CanaryPanel (K_train for concentration, K_eval for evaluation)
    leakcert_runtime : deployed runtime with all 4 components active
    config           : ExperimentConfig
    """

    def __init__(
        self,
        target_service: CompletionService,
        ref_service: Optional[CompletionService],
        panel: CanaryPanel,
        leakcert_runtime=None,
        config: Optional[ExperimentConfig] = None,
    ):
        self.target = target_service
        self.ref = ref_service
        self.panel = panel
        self.runtime = leakcert_runtime
        self.cfg = config or ExperimentConfig()

        # Estimator for KL and certificates
        self.estimator = KLEstimator(target_service, ref_service)
        self.cert_computer = LeakageCertificate()

        Path(self.cfg.output_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Master run method
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """Run the complete evaluation and return a results summary dict."""
        logger.info("=== Starting full LEAKCERT evaluation ===")
        results = {}

        # 1. Compute certificates (Section 5.1–5.2, Tables 1/3)
        logger.info("Step 1: Computing KL estimates and certificates")
        kl_results, cert_table = self.run_certificate_evaluation()
        results["certificate"] = cert_table
        meta = self._result_metadata()
        self._save("certificate/kl_estimates.json",
                   [{"canary_id": r.canary_id, "kl": r.kl_estimate} for r in kl_results],
                   metadata=meta)
        self._save("certificate/tightness_table.json",
                   [{"B": r.query_budget, "cert": r.certificate_nats,
                     "emp_mi": r.empirical_mi_nats, "ratio": r.ratio}
                    for r in cert_table],
                   metadata=meta)

        # 2. Table 4: prior mis-specification sweep
        if self.cfg.run_prior_sweep:
            logger.info("Step 2a: Prior mis-specification sweep (Table 4)")
            prior_results = self.run_prior_sweep(kl_results)
            results["prior_sweep"] = prior_results

        # 3. Extraction success vs. query budget (Table 2, Figure 2)
        logger.info("Step 3: Extraction success evaluation (W4, all defences)")
        extraction_results = self.run_extraction_evaluation(kl_results)
        results["extraction"] = extraction_results

        # 4. Paraphrase robustness (Table 6, W5/W4 ratio)
        logger.info("Step 4: Paraphrase robustness (W5)")
        paraphrase_results = self.run_paraphrase_evaluation()
        results["paraphrase"] = paraphrase_results

        # 5. Utility (W3, Table 5)
        logger.info("Step 5: Utility evaluation (W3 utility benchmark)")
        utility_results = self.run_utility_evaluation()
        results["utility"] = utility_results

        # 6. Table 8: DP epsilon sweep
        if self.cfg.run_dp_sweep:
            logger.info("Step 6: DP epsilon comparison sweep (Table 8)")
            dp_results = self.run_dp_sweep(kl_results)
            results["dp_sweep"] = dp_results

        # 7. E1: multi-seed certificate calibration (tightness ratio CI table)
        logger.info("Step 7: E1 certificate calibration (multi-seed tightness)")
        results["e1_calibration"] = self.run_e1_certificate_calibration()

        # 8. E3: per-mode stress test against LEAKCERT
        logger.info("Step 8: E3 per-mode stress test (9 modes + UCB + Carlini)")
        results["e3_stress"] = self.run_e3_stress_test(kl_results)

        # 9. E6: component ablation
        logger.info("Step 9: E6 component ablation (7 configurations)")
        results["e6_ablation"] = self.run_e6_ablation(kl_results)

        logger.info("=== Evaluation complete ===")
        logger.info(self._summary_table(results))
        return results

    # ------------------------------------------------------------------
    # Step 1: Certificate evaluation
    # ------------------------------------------------------------------

    def run_certificate_evaluation(self) -> tuple[list, list[CertificateTightness]]:
        """Compute per-canary KL estimates and tightness table (Table 3)."""
        train_panel, eval_panel = self.panel.split(n_eval=self.cfg.n_eval_canaries)
        kl_results = self.estimator.estimate_panel(train_panel)

        cert_table = compute_tightness_table(
            kl_results,
            budgets=self.cfg.certificate_budgets,
            canary_set_size=len(self.panel),
            delta=self.cfg.certificate_delta,
        )
        for row in cert_table:
            logger.info(str(row))

        return kl_results, cert_table

    # ------------------------------------------------------------------
    # Step 2: Extraction evaluation
    # ------------------------------------------------------------------

    def run_extraction_evaluation(self, kl_results: list) -> dict:
        """
        Table 2: extraction success rate for all (attacker, defence) pairs.

        Two evaluation modes are run together:

        (A) W4 workload evaluation — one query per W4 template prompt.
            7 templates × n_eval_canaries prompts.  This is the direct,
            non-adaptive baseline and mirrors the attacker-agnostic probing
            described in Section 4.1.  Each prompt is sent exactly once.

        (B) Adaptive attacker evaluation — budget-based, strategy-driven.
            Each attacker uses its full budget B on each eval canary.
            A-adaptive uses UCB mode selection over 9 prompt modes.
            A-Carlini uses LLR ranking over n_samples completions.

        Both (A) and (B) are recorded in the result JSON and logged.
        """
        _, eval_panel = self._stratified_eval_panel()
        w4 = W4CodeSecret(panel=eval_panel)
        w4_samples = w4.samples()

        # Build canary lookup for W4 evaluation
        canary_by_id = {c.canary_id: c for c in eval_panel}

        defences = self._build_defences(kl_results)
        attackers = self._build_attackers()

        extraction_table = {}
        for def_name, service in defences.items():
            extraction_table[def_name] = {}
            logger.info(f"  Defence: {def_name}")

            # ── (A) W4 direct workload evaluation ─────────────────────
            # Use an isolated api_key so W4 budget is independent of
            # subsequent attacker evaluations.
            w4_service = self._measurement_service(service, f"w4_{def_name}")
            w4_by_template: dict[str, list[bool]] = {}
            for sample in w4_samples:
                template = sample.metadata.get("template", "unknown")
                canary = canary_by_id.get(sample.canary_id)
                if canary is None:
                    continue
                results = w4_service.complete(sample.prompt, n_samples=1)
                hit = extraction_hit(canary, results[0].text if results else "")
                w4_by_template.setdefault(template, []).append(hit)

            w4_per_template = {
                t: {"rate": sum(v) / max(len(v), 1), "n": len(v)}
                for t, v in w4_by_template.items()
            }
            n_w4 = sum(len(v) for v in w4_by_template.values())
            n_w4_hit = sum(sum(v) for v in w4_by_template.values())
            extraction_table[def_name]["W4_workload"] = {
                "verbatim_rate": n_w4_hit / max(n_w4, 1),
                "n_success": n_w4_hit,
                "n_total": n_w4,
                "per_template": w4_per_template,
            }
            logger.info(
                f"    W4 workload: {n_w4_hit}/{n_w4} = "
                f"{n_w4_hit / max(n_w4, 1):.2%}"
            )

            # ── (B) Adaptive attacker evaluation ──────────────────────
            # Each attacker gets its own fresh api_key so their budgets
            # are independent of W4 and of each other.
            for atk_name, attacker in attackers.items():
                logger.info(f"    Attacker: {atk_name}")
                atk_service = self._measurement_service(
                    service, f"{atk_name}_{def_name}"
                )
                attack_results = attacker.attack_panel(atk_service, eval_panel)
                metrics = ExtractionMetrics.from_attack_results(
                    attack_results,
                    panel=eval_panel,
                    attack_name=atk_name,
                    defense_name=def_name,
                    query_budget=self.cfg.query_budget,
                    workload_name="W4_adaptive",
                )
                extraction_table[def_name][atk_name] = {
                    "verbatim_rate": metrics.verbatim_rate,
                    "semantic_rate": metrics.semantic_rate,
                    "n_success": metrics.n_success_verbatim,
                    "n_total": metrics.n_total,
                    "per_type": metrics.per_type,
                }
                logger.info(f"      {metrics}")

        self._save("extraction/table2.json", extraction_table,
                   metadata=self._result_metadata(n_queries=len(w4_samples)))
        return extraction_table

    # ------------------------------------------------------------------
    # Step 3: Paraphrase robustness
    # ------------------------------------------------------------------

    def run_paraphrase_evaluation(self) -> dict:
        """
        Table 6: W5/W4 paraphrase robustness ratio per defence.

        Protocol:
          1. Generate W4 from the stratified eval panel:
             len(panel) × 7 unique (canary, template) prompts, one query each.
          2. Generate W5 from W4 (5 paraphrase modes × W4):
             len(W4) × 5 = len(panel) × 35 unique (canary, template, mode) prompts.
          3. Record extraction rate per workload and per paraphrase mode.
          4. Ratio r = W5_rate / W4_rate.
             r ≈ 1.0 → robust (target for LEAKCERT).
             r >> 1.0 → brittle (e.g. regex filter B5 at 7.42× in study).
        """
        _, eval_panel = self._stratified_eval_panel()
        w4 = W4CodeSecret(panel=eval_panel)
        w5 = W5Paraphrase(w4)

        w4_samples = w4.samples()
        w5_samples = w5.samples()

        # Build canary lookup once
        canary_by_id = {c.canary_id: c for c in eval_panel}

        defences = self._build_defences(kl_results=None)
        ratios = {}

        for def_name, service in defences.items():
            logger.info(f"  Paraphrase: {def_name}")

            # W4 and W5 each get isolated api_keys so neither exhausts
            # the other's budget (critical for LEAKCERT throttle logic).
            w4_service = self._measurement_service(service, f"para_w4_{def_name}")
            w5_service = self._measurement_service(service, f"para_w5_{def_name}")

            # ── W4: one query per template prompt ─────────────────────
            n_w4_hit, n_w4 = 0, 0
            for sample in w4_samples:
                canary = canary_by_id.get(sample.canary_id)
                if canary is None:
                    continue
                results = w4_service.complete(sample.prompt, n_samples=1)
                hit = extraction_hit(canary, results[0].text if results else "")
                n_w4_hit += int(hit)
                n_w4 += 1
            w4_rate = n_w4_hit / max(n_w4, 1)

            # ── W5: one query per (paraphrase_mode × template) prompt ─
            # Group results by paraphrase mode so we can report per-mode rates
            w5_by_mode: dict[str, list[bool]] = {}
            for sample in w5_samples:
                canary = canary_by_id.get(sample.canary_id)
                if canary is None:
                    continue
                results = w5_service.complete(sample.prompt, n_samples=1)
                hit = extraction_hit(canary, results[0].text if results else "")
                mode = sample.paraphrase_mode or "unknown"
                w5_by_mode.setdefault(mode, []).append(hit)

            n_w5_hit = sum(sum(v) for v in w5_by_mode.values())
            n_w5 = sum(len(v) for v in w5_by_mode.values())
            w5_rate = n_w5_hit / max(n_w5, 1)

            per_mode = {
                m: {"rate": sum(v) / max(len(v), 1), "n": len(v)}
                for m, v in w5_by_mode.items()
            }
            ratio = w5_rate / w4_rate if w4_rate > 0 else float("inf")

            ratios[def_name] = {
                "w4_rate": w4_rate,
                "w4_n_success": n_w4_hit,
                "w4_n_total": n_w4,
                "w5_rate": w5_rate,
                "w5_n_success": n_w5_hit,
                "w5_n_total": n_w5,
                "ratio": ratio,
                "per_mode": per_mode,
            }
            logger.info(
                f"    W4={w4_rate:.2%} ({n_w4_hit}/{n_w4}), "
                f"W5={w5_rate:.2%} ({n_w5_hit}/{n_w5}), "
                f"ratio={ratio:.3f}×"
            )

        self._save("paraphrase/table6.json", ratios,
                   metadata=self._result_metadata(n_queries=n_w4 + n_w5))
        return ratios

    # ------------------------------------------------------------------
    # Step 4: Utility evaluation
    # ------------------------------------------------------------------

    def run_utility_evaluation(self) -> dict:
        """Compute utility benchmark pass@1 for each defence (Table 5)."""
        from .workloads import W3RealCompletion
        from .metrics import evaluate_pass_at_k

        w3 = W3RealCompletion()
        defences = self._build_defences(kl_results=None)
        utility = {}

        for def_name, service in defences.items():
            logger.info(f"  Utility: {def_name}")
            metrics = evaluate_pass_at_k(service, w3, k=1, n_samples=1)
            utility[def_name] = {
                "pass_at_1": metrics.pass_at_1,
                "n_problems": metrics.n_problems,
            }
            logger.info(f"    pass@1 = {metrics.pass_at_1:.1%}")

        self._save("utility/table5.json", utility, metadata=self._result_metadata())
        return utility

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Table 4: prior mis-specification sweep
    # ------------------------------------------------------------------

    def run_prior_sweep(self, kl_results: list) -> list[dict]:
        """
        Table 4: certificate tightness under 3 prior types (Section 5.2).

          - uniform          : π(k) = 1/|K|,  H(K) = log|K|
          - type_empirical   : π(k) ∝ 1/n_type_k  (type-stratified)
          - type_prefix_empirical : π(k) ∝ empirical prefix frequency

        Returns list of {prior_type, H_K, kl_penalty, cert} dicts.
        """

        n = len(kl_results)
        K = len(self.panel)
        B = self.cfg.query_budget
        delta = self.cfg.certificate_delta

        rows = []
        for prior_type in self.cfg.prior_types:
            pi = self._build_prior(kl_results, prior_type)
            cert_result = self.cert_computer.compute(
                kl_results, B, K, delta, prior=pi
            )
            # KL penalty D_KL(π || Unif_K) from Remark 9
            pi_arr = np.array(pi)
            kl_penalty = float(np.sum(
                pi_arr * np.log(pi_arr * n + 1e-12)  # D_KL(π || Unif)
            ))
            row = {
                "prior_type": prior_type,
                "H_K": cert_result.prior_entropy,
                "kl_penalty": kl_penalty,
                "cert_nats": cert_result.hoeffding_certificate,
            }
            rows.append(row)
            logger.info(
                f"  {prior_type}: H(K)={row['H_K']:.2f}, "
                f"D_KL(π||Unif)={kl_penalty:.2f}, cert={row['cert_nats']:.1f}"
            )

        self._save("certificate/table4_prior_sweep.json", rows,
                   metadata=self._result_metadata())
        return rows

    def _build_prior(self, kl_results: list, prior_type: str) -> list[float]:
        """Build prior weights π(k) for a given prior type (Table 4)."""
        n = len(kl_results)
        if prior_type == "uniform":
            return [1.0 / n] * n

        # Type-empirical: weight inversely proportional to type count
        # (more rare types get higher prior weight per canary)
        type_counts: dict[str, int] = {}
        for r in kl_results:
            t = r.canary_type or "unknown"
            type_counts[t] = type_counts.get(t, 0) + 1

        if prior_type == "type_empirical":
            weights = [1.0 / type_counts.get(r.canary_type or "unknown", 1)
                       for r in kl_results]
        else:
            # type_prefix_empirical: also weight by inverse KL (higher KL → higher prior)
            # Reflects that attackers know which canaries are most extractable.
            kl_vals = np.array([r.kl_estimate for r in kl_results])
            kl_vals = kl_vals / (kl_vals.sum() + 1e-12)
            type_w = np.array([
                1.0 / type_counts.get(r.canary_type or "unknown", 1)
                for r in kl_results
            ])
            weights = list(0.5 * type_w / (type_w.sum() + 1e-12)
                           + 0.5 * kl_vals)

        total = sum(weights)
        return [w / total for w in weights]

    # ------------------------------------------------------------------
    # Table 8: DP epsilon comparison sweep
    # ------------------------------------------------------------------

    def run_dp_sweep(self, kl_results: list) -> list[dict]:
        """
        Table 8: compare LEAKCERT certificate vs. analytic DP bound for
        ε ∈ {1,2,4,8,16} and the non-private baseline (Section 5.7).

        Requires kl_results from the actual fine-tuned model.
        For DP models the certificate shrinks quadratically with ε (since
        per-query KL ≤ ε²/2 for (ε,δ)-DP models).
        """
        rows = []
        K = len(self.panel)
        B = self.cfg.query_budget
        delta = self.cfg.certificate_delta

        # Baseline (non-private)
        cert_result = self.cert_computer.compute(kl_results, B, K, delta)
        rows.append({
            "configuration": "no_DP",
            "leakcert_cert": cert_result.hoeffding_certificate,
            "dp_bound": None,
            "ratio": None,
        })
        logger.info(f"  no_DP: cert={cert_result.hoeffding_certificate:.1f}")

        # DP sweep: for each ε, the per-query KL ≤ ε²/2
        # We simulate the KL estimates a DP-trained model would produce
        # by clamping observed KLs to ε²/2.  In a real run, kl_results
        # would come from an actual DP fine-tuned model for each ε.
        from ..certificate.certificate import LeakageCertificate
        for eps in self.cfg.dp_epsilons:
            dp_kl_cap = (eps ** 2) / 2.0
            # Clamp per-canary KL to the DP upper bound
            from ..certificate.kl_estimator import PerCanaryKL
            clamped = [
                PerCanaryKL(
                    canary_id=r.canary_id,
                    kl_estimate=min(r.kl_estimate, dp_kl_cap),
                    log_p_target=r.log_p_target,
                    log_p_ref=r.log_p_ref,
                    n_tokens=r.n_tokens,
                    canary_type=r.canary_type,
                )
                for r in kl_results
            ]
            cert_result = self.cert_computer.compute(clamped, B, K, delta)
            raw_dp_analytic = LeakageCertificate.dp_composition_certificate(eps, B, K)
            dp_analytic = min(raw_dp_analytic, cert_result.prior_entropy)
            ratio = cert_result.hoeffding_certificate / dp_analytic
            rows.append({
                "configuration": f"DP_eps{eps}",
                "epsilon": eps,
                "leakcert_cert": cert_result.hoeffding_certificate,
                "raw_leakcert_cert": cert_result.raw_hoeffding_certificate,
                "dp_bound": dp_analytic,
                "raw_dp_bound": raw_dp_analytic,
                "entropy_H_K_nats": cert_result.prior_entropy,
                "entropy_cap_applied": (
                    cert_result.entropy_cap_applied
                    or raw_dp_analytic > cert_result.prior_entropy
                ),
                "entropy_cap_pass": (
                    cert_result.hoeffding_certificate <= cert_result.prior_entropy + 1e-12
                    and dp_analytic <= cert_result.prior_entropy + 1e-12
                ),
                "ratio": ratio,
            })
            logger.info(
                f"  DP ε={eps}: cert={cert_result.hoeffding_certificate:.1f}, "
                f"dp_analytic={dp_analytic:.1f}, ratio={ratio:.3f}"
            )

        # Label all rows so downstream tools know this is simulated
        for row in rows:
            row["simulation_note"] = (
                "KL clamped at eps^2/2 to simulate DP training. "
                "Real Table 8 requires separate DP-SGD fine-tuned models."
            )
        self._save("dp_comparison/table8.json", rows,
                   metadata=self._result_metadata())
        return rows

    # ------------------------------------------------------------------
    # E1: Certificate calibration (multi-seed, multi-panel-size sweep)
    # ------------------------------------------------------------------

    def run_e1_certificate_calibration(self) -> list[dict]:
        """
        E1: Tightness ratio mean ± 95% CI over multiple seeds and panel sizes.

        For each (B, n, seed) triple:
          1. Draw a T1-only panel of exactly n canaries with that seed
          2. Estimate per-canary KL on the test service
          3. Compute Hoeffding cert L̂_B (Theorem 10)
          4. Compute empirical MI Î(K;Y^B) via MINE / analytic approximation
          5. Record tightness ratio r = L̂_B / Î  (study target ≤ 1.3×)

        Uses canary_set_size = actual panel size (not the requested n) to
        avoid the mismatch when T2/T3/T4 canaries inflate the panel.
        """
        from ..canary.generator import CanaryGenerator
        from ..certificate.kl_estimator import KLEstimator

        budgets = self.cfg.certificate_budgets
        panel_sizes = [500, 1_000, 5_000, len(self.panel)]
        seeds = self.cfg.seeds[: self.cfg.n_seeds]
        rows = []

        for n in panel_sizes:
            for seed in seeds:
                # Generate a panel and filter to T1 (literal) canaries only.
                # generate_panel(include_paraphrase=False) still appends 50 T3
                # + 50 T4, so we filter by CanaryType.LITERAL explicitly.
                from ..canary.types import CanaryType
                gen = CanaryGenerator(n_canaries=n, n_eval=0, seed=seed)
                raw_panel = gen.generate_panel(include_paraphrase=False)
                t1_only = [c for c in raw_panel
                           if c.canary_type == CanaryType.LITERAL]
                if not t1_only:
                    logger.warning(f"E1 n={n} seed={seed}: no T1 canaries found")
                    continue
                from ..canary.types import CanaryPanel as _CP
                mini_panel = _CP(t1_only)
                actual_n = len(t1_only)
                kl_res = self.estimator.estimate_panel(mini_panel)
                kl_vals = [r.kl_estimate for r in kl_res]

                for B in budgets:
                    cert = self.cert_computer.compute(
                        kl_res, B, actual_n, self.cfg.certificate_delta
                    )
                    # Empirical MI via neural MINE (Belghazi et al., ICML 2018).
                    # Uses a fixed per-query noise (sigma_query_nats=0.1 nat)
                    # independent of the KL distribution, so MI scales
                    # monotonically with KL magnitude.
                    # Fallback: analytic B*mean(KL) when torch is unavailable.
                    raw_emp_mi = KLEstimator.mine_estimate(
                        kl_vals, query_budget=B, canary_set_size=actual_n,
                        use_neural=True
                    )
                    emp_mi = min(raw_emp_mi, cert.prior_entropy)
                    tightness = (
                        cert.hoeffding_certificate / emp_mi
                        if emp_mi > 0 and raw_emp_mi <= cert.prior_entropy + 1e-12
                        else None
                    )
                    rows.append({
                        "B": B, "n": actual_n, "seed": seed,
                        "hoeffding_cert": cert.hoeffding_certificate,
                        "raw_hoeffding_cert": cert.raw_hoeffding_certificate,
                        "bernstein_cert": cert.bernstein_certificate,
                        "raw_bernstein_cert": cert.raw_bernstein_certificate,
                        "empirical_mi": emp_mi,
                        "raw_empirical_mi": raw_emp_mi,
                        "entropy_H_K_nats": cert.prior_entropy,
                        "entropy_cap_applied": cert.entropy_cap_applied or raw_emp_mi > cert.prior_entropy,
                        "entropy_cap_pass": (
                            cert.hoeffding_certificate <= cert.prior_entropy + 1e-12
                            and cert.bernstein_certificate <= cert.prior_entropy + 1e-12
                            and emp_mi <= cert.prior_entropy + 1e-12
                        ),
                        "empirical_mi_source": "neural_mine_fixed_noise",
                        "tightness_ratio": tightness,
                        "mean_kl": cert.mean_kl,
                        "std_kl": cert.std_kl,
                    })
                    logger.debug(
                        f"E1 n={actual_n} B={B} seed={seed}: "
                        f"cert={cert.hoeffding_certificate:.2f} "
                        f"emp_mi(neural,capped)={emp_mi:.2f} ratio={tightness}×"
                    )

        # Aggregate: mean ± 95% CI per (B, n) cell
        import statistics
        cell_data: dict[tuple, list] = {}
        for row in rows:
            key = (row["B"], row["n"])
            cell_data.setdefault(key, []).append(row)
        ci_table = []
        for (B, n), cell_rows in cell_data.items():
            certs = [r["hoeffding_cert"] for r in cell_rows]
            ratios = [r["tightness_ratio"] for r in cell_rows
                      if r["tightness_ratio"] is not None]
            mean_cert = statistics.mean(certs)
            sd_cert = statistics.stdev(certs) if len(certs) > 1 else 0.0
            mean_ratio = statistics.mean(ratios) if ratios else None
            ci_table.append({
                "B": B, "n": n,
                "mean_cert": mean_cert,
                "ci95_cert": 1.96 * sd_cert / (len(certs) ** 0.5),
                "mean_tightness": mean_ratio,
                "target_met": mean_ratio <= 1.3 if ratios else None,
                "n_seeds": len(certs),
            })
            logger.info(
                f"  E1 B={B} n={n}: cert={mean_cert:.2f} "
                f"tightness={mean_ratio:.2f}× "
                f"({'≤1.3×' if mean_ratio <= 1.3 else '>1.3× FAIL'})"
            )

        self._save("certificate/e1_calibration.json",
                   {"raw": rows, "ci_table": ci_table},
                   metadata=self._result_metadata())
        return ci_table

    # ------------------------------------------------------------------
    # E3: Adaptive/strong attack stress test
    # ------------------------------------------------------------------

    def run_e3_stress_test(self, kl_results: list) -> dict:
        """
        E3: Per-mode isolation + combined UCB + Carlini, against LEAKCERT.

        Each of the 9 prompt modes is run as the SOLE mode for its attacker
        (using locked_mode), so results are truly per-mode, not round-robin.
        Then full UCB-adaptive and Carlini are run as combined attackers.

        Goal: no single mode or combined attacker exceeds the certificate.
        """
        from ..attacks.a_adaptive import AAdaptive, PARAPHRASE_MODES
        from ..attacks.a_carlini import ACarlini

        _, eval_panel = self._stratified_eval_panel()
        all_defences = self._build_defences(kl_results)
        # E3 is run against LEAKCERT; fall back to last defence if not present
        leakcert_service = all_defences.get(
            "LEAKCERT", list(all_defences.values())[-1]
        )
        defences = {"LEAKCERT": leakcert_service}
        B = self.cfg.query_budget
        stress_results = {}

        # --- Nine per-mode locked attackers ---
        # Each (mode, defence) gets an isolated api_key so per-mode budgets
        # are independent — crucial for locked_mode being a true isolation test.
        for mode in PARAPHRASE_MODES:
            attacker = AAdaptive(
                budget=B, locked_mode=mode, ref_service=self.ref
            )
            attacker_name = f"A_mode_{mode}"
            for def_name, service in defences.items():
                svc = self._measurement_service(service, f"e3_{attacker_name}_{def_name}")
                results = attacker.attack_panel(svc, eval_panel)
                metrics = ExtractionMetrics.from_attack_results(
                    results, attack_name=attacker_name, defense_name=def_name
                )
                stress_results.setdefault(def_name, {})[attacker_name] = {
                    "verbatim_rate": metrics.verbatim_rate,
                    "n_success": metrics.n_success_verbatim,
                    "n_total": metrics.n_total,
                }
                logger.info(f"  E3 {attacker_name} vs {def_name}: "
                            f"{metrics.verbatim_rate:.2%}")

        # --- Full UCB-adaptive (9 modes, UCB allocation) ---
        ucb_attacker = AAdaptive(budget=B, use_ucb=True, ref_service=self.ref)
        for def_name, service in defences.items():
            svc = self._measurement_service(service, f"e3_ucb_{def_name}")
            results = ucb_attacker.attack_panel(svc, eval_panel)
            metrics = ExtractionMetrics.from_attack_results(
                results, attack_name="A_adaptive_UCB", defense_name=def_name
            )
            stress_results.setdefault(def_name, {})["A_adaptive_UCB"] = {
                "verbatim_rate": metrics.verbatim_rate,
                "n_success": metrics.n_success_verbatim,
                "n_total": metrics.n_total,
            }

        # --- Carlini-style LLR-ranked attack ---
        carlini = ACarlini(
            budget=B, ref_service=self.ref, n_samples=self.cfg.carlini_n_samples
        )
        for def_name, service in defences.items():
            svc = self._measurement_service(service, f"e3_carlini_{def_name}")
            results = carlini.attack_panel(svc, eval_panel)
            metrics = ExtractionMetrics.from_attack_results(
                results, attack_name="A_Carlini", defense_name=def_name
            )
            stress_results.setdefault(def_name, {})["A_Carlini"] = {
                "verbatim_rate": metrics.verbatim_rate,
                "n_success": metrics.n_success_verbatim,
                "n_total": metrics.n_total,
            }

        self._save("extraction/e3_stress_test.json", stress_results,
                   metadata=self._result_metadata())
        return stress_results

    # ------------------------------------------------------------------
    # E6: Component ablation
    # ------------------------------------------------------------------

    def run_e6_ablation(self, kl_results: list) -> list[dict]:
        """
        E6: Ablate each of the four LEAKCERT runtime components.

        Each configuration is built by passing the exact ablation flags
        directly into RuntimeConfig (all four flags are now real fields).

        Configs:
          all              – full LEAKCERT (C1+C2+C3+C4)
          no_accounting    – drop C1 (KL budget tracking)
          no_rate_limit    – drop C2 (per-key rate limiter)
          no_refusal       – drop C3 (uncertainty refusal)
          no_suppression   – drop C4 (target-string suppression)
          only_rate_limit  – C2 only  (matches B4 baseline)
          only_suppression – C4 only  (matches B5 baseline)
        """
        from ..runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig

        ablation_configs = {
            "all":              dict(use_accounting=True,  use_rate_limit=True,
                                    use_refusal=True,  use_suppression=True),
            "no_accounting":    dict(use_accounting=False, use_rate_limit=True,
                                    use_refusal=True,  use_suppression=True),
            "no_rate_limit":    dict(use_accounting=True,  use_rate_limit=False,
                                    use_refusal=True,  use_suppression=True),
            "no_refusal":       dict(use_accounting=True,  use_rate_limit=True,
                                    use_refusal=False, use_suppression=True),
            "no_suppression":   dict(use_accounting=True,  use_rate_limit=True,
                                    use_refusal=True,  use_suppression=False),
            "only_rate_limit":  dict(use_accounting=False, use_rate_limit=True,
                                    use_refusal=False, use_suppression=False),
            "only_suppression": dict(use_accounting=False, use_rate_limit=False,
                                    use_refusal=False, use_suppression=True),
        }

        import math as _math
        B = self.cfg.query_budget
        K = len(self.panel)
        delta = self.cfg.certificate_delta
        _, eval_panel = self._stratified_eval_panel()
        attacker = AAdaptive(budget=B, use_ucb=True, ref_service=self.ref)
        rows = []

        for config_name, flags in ablation_configs.items():
            runtime = LeakCertRuntime(
                service=self.target,
                kl_estimator=KLEstimator(self.target, self.ref),
                config=RuntimeConfig(query_budget=B, **flags),
            )
            service = _RuntimeServiceAdapter(runtime)
            results = attacker.attack_panel(service, eval_panel)
            metrics = ExtractionMetrics.from_attack_results(
                results, attack_name="A_adaptive_UCB", defense_name=config_name
            )

            # Per-config certificate validity:
            # - use_rate_limit=False  → no query budget → certificate is vacuous
            # - use_accounting=False  → no KL tracking → certificate is vacuous
            # - all other flags don't change the certificate formula
            rate_limited = flags.get("use_rate_limit", True)
            accounting_on = flags.get("use_accounting", True)
            if rate_limited and accounting_on:
                cert = self.cert_computer.compute(kl_results, B, K, delta)
                cert_nats = cert.hoeffding_certificate
                cert_advantage = cert.certified_extraction_advantage
                is_vacuous = LeakageCertificate.is_vacuous(cert_nats, K)
            else:
                # Certificate is vacuous: no budget or no KL tracking
                cert_nats = _math.log(K)   # trivial upper bound
                cert_advantage = None
                is_vacuous = True

            rows.append({
                "config": config_name,
                "flags": flags,
                "verbatim_rate": metrics.verbatim_rate,
                "n_success": metrics.n_success_verbatim,
                "n_total": metrics.n_total,
                "certificate_nats": cert_nats,
                "is_vacuous": is_vacuous,
                "certified_advantage": cert_advantage,
            })
            vacuous_str = " [VACUOUS]" if is_vacuous else ""
            logger.info(
                f"  E6 {config_name}: {metrics.verbatim_rate:.2%} "
                f"(cert={cert_nats:.1f}{vacuous_str})"
            )

        self._save("extraction/e6_ablation.json", rows,
                   metadata=self._result_metadata())
        return rows

    # ------------------------------------------------------------------
    # Per-measurement budget isolation for LEAKCERT
    # ------------------------------------------------------------------

    def _measurement_service(self, service, measurement_id: str):
        """
        Return a service with an isolated KL/query budget for LEAKCERT.

        Problem: _RuntimeServiceAdapter uses a fixed api_key, so every
        call to complete() inside a single ExperimentRunner run drains
        the same per-key budget.  If W4 workload, A-fixed, A-adaptive,
        … all use api_key="eval_key", LEAKCERT throttles later attackers
        after the earlier ones exhaust the budget — artificially inflating
        LEAKCERT's apparent defence strength.

        Fix: create a fresh adapter with a unique api_key per measurement
        so each (workload, attacker) × defence combination gets its own
        independent budget window.
        """
        # Use service.runtime (not self.runtime) so isolation works even when
        # _build_defences() created a local runtime that wasn't stored in self.runtime.
        if isinstance(service, _RuntimeServiceAdapter):
            return _RuntimeServiceAdapter(
                service.runtime, api_key=f"eval_{measurement_id}"
            )
        return service

    # ------------------------------------------------------------------
    # Stratified eval panel (≥50 canaries per type, internal review requirement)
    # ------------------------------------------------------------------

    def _stratified_eval_panel(self):
        """
        Return (train_panel, eval_panel) stratified across both type AND
        subtype, so the eval set is not dominated by a single secret format.

        Strategy:
          For each canary type (T1-T4), group by subtype and sample evenly
          across subtypes up to n_eval_per_type total per type.
          This prevents T1-only-aws_key bias that occurs with [:n] slicing.
        """
        import math as _math
        from ..canary.types import CanaryPanel

        n_per_type = self.cfg.n_eval_per_type
        all_canaries = list(self.panel)

        # Group by (type, subtype)
        by_type_subtype: dict[str, dict[str, list]] = {}
        for c in all_canaries:
            t_key = (c.canary_type.value
                     if hasattr(c.canary_type, "value") else str(c.canary_type))
            s_key = getattr(c, "subtype", "default") or "default"
            by_type_subtype.setdefault(t_key, {}).setdefault(s_key, []).append(c)

        eval_canaries = []
        for t_val, subtype_map in by_type_subtype.items():
            n_subtypes = len(subtype_map)
            per_subtype = max(1, _math.ceil(n_per_type / n_subtypes))
            type_selected = []
            for s_val, canaries in subtype_map.items():
                # Deterministic subsample: evenly spaced indices
                step = max(1, len(canaries) // per_subtype)
                chosen = [canaries[i] for i in range(0, len(canaries), step)]
                type_selected.extend(chosen[:per_subtype])
            # Trim to n_per_type (may be slightly over due to ceil)
            eval_canaries.extend(type_selected[:n_per_type])
            if len(type_selected) < n_per_type:
                logger.warning(
                    f"Type {t_val}: only {len(type_selected)} canaries "
                    f"(target {n_per_type})"
                )

        if not eval_canaries:
            return self.panel.split(n_eval=self.cfg.n_eval_canaries)

        eval_ids = {c.canary_id for c in eval_canaries}
        train_canaries = [c for c in all_canaries if c.canary_id not in eval_ids]
        return CanaryPanel(train_canaries), CanaryPanel(eval_canaries)

    # ------------------------------------------------------------------
    # Result metadata (E8 reproducibility)
    # ------------------------------------------------------------------

    def _result_metadata(self, n_queries: int = 0) -> dict:
        """Build E8-compliant metadata dict for embedding in every result."""
        from .e_scenarios import build_result_metadata
        return build_result_metadata(
            seed=self.cfg.seed,
            model_id=getattr(self.target, "model_name", "unknown"),
            n_total_queries=n_queries,
            gpu_type=self.cfg.gpu_type,
            gpu_hours=self.cfg.gpu_hours,
            region=self.cfg.cloud_region,
            git_commit=self.cfg.git_commit,
            leakcert_version=self.cfg.leakcert_version,
        )

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    def _build_defences(self, kl_results) -> dict:
        """Build the defence wrappers B1–B5 and LEAKCERT."""
        defences = {}

        if self.cfg.run_b1_no_defense:
            defences["B1_no_defense"] = NoDefense(self.target)

        if self.cfg.run_b2_temperature:
            for tau in self.cfg.b2_temperatures:
                defences[f"B2_temp_{tau}"] = TemperatureDefense(self.target, tau)

        if self.cfg.run_b3_top_p:
            defences["B3_top_p_0.7"] = TopPDefense(self.target, 0.7)

        # B4: rate limit only (1,000 queries per API key per day)
        if self.cfg.run_b4_rate_limit:
            defences["B4_rate_limit"] = RateLimitDefense(
                self.target,
                queries_per_day=self.cfg.b4_queries_per_day,
            )

        if self.cfg.run_b5_content_filter:
            defences["B5_content_filter"] = ContentFilterDefense(self.target)

        if self.cfg.run_leakcert and self.runtime is not None:
            defences["LEAKCERT"] = _RuntimeServiceAdapter(self.runtime)
        elif self.cfg.run_leakcert:
            from ..runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig
            runtime = LeakCertRuntime(
                service=self.target,
                kl_estimator=KLEstimator(self.target, self.ref),
                config=RuntimeConfig(query_budget=self.cfg.query_budget),
            )
            defences["LEAKCERT"] = _RuntimeServiceAdapter(runtime)

        return defences

    def _build_attackers(self) -> dict:
        """Build all attackers (A-fixed, A-grid, A-adaptive, A-greedy-LRT, A-Carlini)."""
        attackers = {}
        B = self.cfg.query_budget

        if self.cfg.run_a_fixed:
            attackers["A_fixed"] = AFixed(budget=B)
        if self.cfg.run_a_grid:
            attackers["A_grid"] = AGrid(budget=B)
        if self.cfg.run_a_adaptive:
            attackers["A_adaptive"] = AAdaptive(
                budget=B, use_ucb=True, ref_service=self.ref
            )
        if self.cfg.run_a_greedy_lrt and self.ref is not None:
            attackers["A_greedy_LRT"] = AGreedyLRT(budget=B, ref_service=self.ref)
        # B7 Carlini attack (requires ref model for LLR ranking)
        if self.cfg.run_a_carlini:
            attackers["A_Carlini"] = ACarlini(
                budget=B,
                ref_service=self.ref,
                n_samples=self.cfg.carlini_n_samples,
            )

        return attackers

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    def _save(self, relative_path: str, data, metadata: dict = None) -> None:
        """Save result JSON, embedding E8 reproducibility metadata if provided."""
        full_path = Path(self.cfg.output_dir) / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if metadata is not None:
            if isinstance(data, dict):
                data = {"_meta": metadata, **data}
            else:
                data = {"_meta": metadata, "data": data}
        with open(full_path, "w") as f:
            json.dump(data, f, indent=2, default=_json_default)
        logger.debug(f"Saved {full_path}")

    @staticmethod
    def _summary_table(results: dict) -> str:
        lines = ["\n=== LEAKCERT Results Summary ==="]
        if "certificate" in results:
            for row in results["certificate"]:
                lines.append(f"  {row}")
        if "extraction" in results:
            lines.append("\nExtraction rates (A-adaptive):")
            for defense, atk_results in results["extraction"].items():
                for atk, m in atk_results.items():
                    if "adaptive" in atk.lower():
                        lines.append(f"  {defense}: {m['verbatim_rate']:.2%}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adapter: wrap LeakCertRuntime as a CompletionService
# ---------------------------------------------------------------------------

class _RuntimeServiceAdapter(CompletionService):
    """Wraps LeakCertRuntime as a CompletionService for evaluation."""

    def __init__(self, runtime, api_key: str = "eval_key"):
        super().__init__()
        self.runtime = runtime
        self.api_key = api_key

    def complete(self, prompt: str, n_samples: int = 1):
        from ..model.completion_service import CompletionResult
        results = []
        for _ in range(n_samples):
            decision = self.runtime.handle_query(self.api_key, prompt)
            results.append(CompletionResult(
                text=decision.completion or "",
                token_ids=[],
                log_probs=[],
                was_refused=decision.outcome != "emit",
            ))
        return results

    def complete_many(
        self,
        prompts: list[str],
        n_samples: int = 1,
        batch_size: int = 8,
    ):
        """Batch target generation while preserving per-query runtime decisions.

        The default CompletionService fallback calls complete() prompt by prompt.
        That is correct but very slow for W5, because LEAKCERT also performs
        KL accounting per emitted completion.  For the common n_samples=1 path
        we can batch the target model generation, then replay the runtime
        accounting/refusal/suppression logic per prompt.
        """
        if n_samples != 1:
            return super().complete_many(prompts, n_samples=n_samples, batch_size=batch_size)

        import time

        from ..model.completion_service import CompletionResult
        from ..runtime.leakcert_runtime import REFUSAL_TEXT, RuntimeDecision

        outputs: list[list[CompletionResult] | None] = [None] * len(prompts)
        pending: list[tuple[int, str, float]] = []

        for idx, prompt in enumerate(prompts):
            t0 = time.time()
            if self.runtime.config.use_rate_limit:
                allowed, _reason = self.runtime.rate_limiter.check(self.api_key)
                if not allowed:
                    decision = RuntimeDecision(
                        api_key=self.api_key,
                        prompt=prompt,
                        outcome="throttled",
                        completion=REFUSAL_TEXT,
                        latency_ms=(time.time() - t0) * 1000,
                        queries_used=self.runtime.rate_limiter.get_state(self.api_key).query_count,
                    )
                    self.runtime._log(decision)
                    outputs[idx] = [CompletionResult(
                        text=decision.completion or "",
                        token_ids=[],
                        log_probs=[],
                        was_refused=True,
                    )]
                    continue
            pending.append((idx, prompt, t0))

        if pending:
            batch_results = self.runtime.service.complete_many(
                [prompt for _idx, prompt, _t0 in pending],
                n_samples=1,
                batch_size=batch_size,
            )
            for (idx, prompt, t0), results in zip(pending, batch_results):
                result = results[0] if results else CompletionResult("", [], [])
                completion_text = result.text

                kl_contrib = 0.0
                if self.runtime.config.use_accounting and self.runtime.kl_estimator is not None:
                    try:
                        kl_contrib = self.runtime.kl_estimator.streaming_kl_contribution(
                            prompt, completion_text
                        )
                    except Exception as exc:
                        logger.debug("KL estimation error: %s", exc)

                if self.runtime.config.use_rate_limit:
                    self.runtime.rate_limiter.record_query(self.api_key, kl_contrib)

                refusal_score = 0.0
                if self.runtime.config.use_refusal:
                    refusal_decision = self.runtime.refusal.decide(completion_text)
                    refusal_score = refusal_decision.score
                    if refusal_decision.should_refuse:
                        decision = RuntimeDecision(
                            api_key=self.api_key,
                            prompt=prompt,
                            outcome="refused",
                            completion=REFUSAL_TEXT,
                            latency_ms=(time.time() - t0) * 1000,
                            kl_contribution=kl_contrib,
                            queries_used=self.runtime.rate_limiter.get_state(self.api_key).query_count
                            if self.runtime.config.use_rate_limit else 0,
                            refusal_score=refusal_score,
                        )
                        self.runtime._log(decision)
                        outputs[idx] = [CompletionResult(
                            text=decision.completion or "",
                            token_ids=[],
                            log_probs=[],
                            was_refused=True,
                        )]
                        continue

                outcome = "emit"
                if self.runtime.config.use_suppression:
                    supp = self.runtime.suppression.filter(completion_text)
                    if supp.was_suppressed:
                        completion_text = supp.suppressed_text
                        outcome = "suppressed"

                decision = RuntimeDecision(
                    api_key=self.api_key,
                    prompt=prompt,
                    outcome=outcome,
                    completion=completion_text,
                    latency_ms=(time.time() - t0) * 1000,
                    kl_contribution=kl_contrib,
                    queries_used=self.runtime.rate_limiter.get_state(self.api_key).query_count
                    if self.runtime.config.use_rate_limit else 0,
                    refusal_score=refusal_score,
                )
                self.runtime._log(decision)
                outputs[idx] = [CompletionResult(
                    text=decision.completion or "",
                    token_ids=[],
                    log_probs=[],
                    was_refused=decision.outcome != "emit",
                )]

        return [result if result is not None else [] for result in outputs]

    def log_probability(self, prompt: str, completion: str) -> float:
        return self.runtime.service.log_probability(prompt, completion)

    def per_token_log_probs(self, prompt: str, completion: str) -> list[float]:
        return self.runtime.service.per_token_log_probs(prompt, completion)


def _json_default(obj):
    """JSON serialisation fallback."""
    if hasattr(obj, "__float__"):
        return float(obj)
    if hasattr(obj, "__int__"):
        return int(obj)
    return str(obj)
