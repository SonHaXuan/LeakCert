#!/usr/bin/env python3
"""
W1 – Canary Fine-tune Evaluation.

Pipeline:
  1. Generate canary panel (T1–T4, |K|=10^4)
  2. Inject canaries into corpus (each exactly once)
  3. Fine-tune Code-Small / Code-Mid on injected corpus
  4. Compute per-canary KL estimates and Theorem 10 certificate
  5. Run A-adaptive extraction across budgets B ∈ {10^2, ..., 10^5}
  6. Report Table 1 (certificate sweep) and Figure 2 (extraction vs. budget)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from leakcert.canary.generator import CanaryGenerator
from leakcert.canary.injector import CorpusInjector
from leakcert.certificate.certificate import LeakageCertificate
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.attacks.a_adaptive import AAdaptive
from leakcert.model.fine_tuner import CanaryFineTuner, FineTuneConfig
from leakcert.model.backend_model import BackendCompletionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main(args):
    cfg = yaml.safe_load(open(args.config))
    output_dir = Path(cfg.get("output_dir", "./results/w1"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Generate canary panel ──────────────────────────────────────
    logger.info("Generating canary panel...")
    n_per_type = cfg["canary"].get("n_eval_per_type", 283)
    gen = CanaryGenerator(
        n_canaries=cfg["canary"]["n_canaries"],
        n_eval=n_per_type * 4,
        seed=cfg["canary"]["seed"],
    )
    panel = gen.generate_panel(
        include_paraphrase=cfg["canary"].get("include_paraphrase", True),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    # stratified_subset() takes the first n_per_type of each CanaryType from the
    # injected panel — guaranteeing eval_panel ⊂ panel (all eval canaries were
    # fine-tuned on) and exactly 283 per type.  panel.split() was random and
    # produced imbalanced types; generate_eval_panel() generated a disjoint set.
    eval_panel = panel.stratified_subset(n_per_type)
    train_panel = panel  # KL estimated on all injected canaries
    logger.info(
        f"Panel: {len(panel)} canaries total; "
        f"eval: {len(eval_panel)} ({n_per_type}/type × 4 types)"
    )

    # Save canary manifest (non-secret metadata only)
    with open(output_dir / "canary_manifest.json", "w") as f:
        json.dump([
            {"id": c.canary_id, "type": c.canary_type.value, "context": c.context}
            for c in eval_panel
        ], f, indent=2)

    # ── 2. Inject canaries into corpus ────────────────────────────────
    logger.info("Injecting canaries into corpus...")
    injector = CorpusInjector(seed=cfg["canary"]["seed"])
    corpus_path = cfg.get("corpus", {}).get("path", "./data/corpus.jsonl")
    injected_path = str(output_dir / "corpus_with_canaries.jsonl")

    if Path(corpus_path).exists():
        manifest = injector.inject_into_dataset(corpus_path, panel, injected_path)
        injector.save_manifest(manifest, panel, output_dir / "injection_manifest.json")
    elif args.allow_synthetic:
        logger.warning(
            f"Corpus not found at {corpus_path}. "
            "Using synthetic corpus — results NOT valid for study run."
        )
        _create_synthetic_corpus(injected_path, panel)
    else:
        logger.error(
            f"Corpus not found at {corpus_path}. "
            "Provide a real corpus or pass --allow-synthetic for testing only."
        )
        sys.exit(1)

    # ── 3. Fine-tune ──────────────────────────────────────────────────
    ft_cfg = cfg.get("finetune", {})
    target_model_name = cfg["model"].get("target_model_small",
                                         cfg["model"].get("target_model", "local-test-model"))
    checkpoint_dir = ft_cfg.get("output_dir", str(output_dir / "target_model"))

    if not Path(checkpoint_dir).exists() or args.force_retrain:
        if not args.allow_synthetic and not Path(injected_path).exists():
            logger.error(
                "Cannot fine-tune: injected corpus missing. "
                "Pass --allow-synthetic for testing only."
            )
            sys.exit(1)
        logger.info(f"Fine-tuning {target_model_name}...")
        tuner = CanaryFineTuner(FineTuneConfig(
            model_name_or_path=target_model_name,
            output_dir=checkpoint_dir,
            corpus_path=injected_path,
            num_train_epochs=ft_cfg.get("num_train_epochs", 3),
            per_device_train_batch_size=ft_cfg.get("per_device_train_batch_size", 4),
            gradient_accumulation_steps=ft_cfg.get("gradient_accumulation_steps", 8),
            learning_rate=ft_cfg.get("learning_rate", 2e-5),
            max_seq_length=ft_cfg.get("max_seq_length", 512),
            fp16=ft_cfg.get("fp16", True),
            use_dp=ft_cfg.get("use_dp", False),
        ))
        tuner.train()
    else:
        logger.info(f"Loading existing checkpoint from {checkpoint_dir}")

    # ── 4. Load models and compute certificates ───────────────────────
    logger.info("Loading models...")
    target_service = BackendCompletionService(
        checkpoint_dir,
        temperature=cfg["model"].get("temperature", 1.0),
        max_new_tokens=cfg["model"].get("max_new_tokens", 128),
    )
    ref_service = BackendCompletionService(
        target_model_name,
        temperature=1.0,
        max_new_tokens=128,
    )

    logger.info("Computing KL estimates...")
    estimator = KLEstimator(target_service, ref_service)
    kl_results = estimator.estimate_panel(train_panel)

    # Certificate sweep (Table 1)
    cert_computer = LeakageCertificate()
    budgets = cfg["certificate"].get(
        "budgets", [1, 10, 100, 1000, 5000, 10_000, 50_000, 100_000, 1_000_000]
    )
    delta = cfg["certificate"].get("delta", 0.01)
    K = len(panel)

    logger.info("\n=== Table 1: Certificate sweep ===")
    cert_table = []
    for B in budgets:
        result = cert_computer.compute(kl_results, B, K, delta)
        is_vac = LeakageCertificate.is_vacuous(result.hoeffding_certificate, K)
        ext_bound = result.extraction_prob_bound
        row = {
            "B": B,
            "cert_nats": round(result.hoeffding_certificate, 3),
            "extraction_prob_bound": round(ext_bound, 6) if ext_bound else None,
            "vacuous": is_vac,
        }
        cert_table.append(row)
        logger.info(
            f"  B={B:>8d} | cert={result.hoeffding_certificate:8.3f} nats | "
            f"P(extract)≤{ext_bound:.4%} | {'vacuous' if is_vac else 'valid'}"
        )

    with open(output_dir / "table1_certificate_sweep.json", "w") as f:
        json.dump(cert_table, f, indent=2)

    # ── 5. Extraction success vs. budget (Figure 2) ───────────────────
    logger.info("\n=== Figure 2: Extraction vs. budget ===")
    extraction_results = []
    for B in [100, 1_000, 10_000, 100_000]:
        if B > cfg["evaluation"].get("query_budget", 10_000) * 10:
            continue
        attacker = AAdaptive(budget=B)
        results = attacker.attack_panel(target_service, eval_panel)
        rate = attacker.extraction_success_rate(results)
        extraction_results.append({"B": B, "extraction_rate": round(rate, 4)})
        logger.info(f"  B={B:>8d} | extraction rate = {rate:.2%}")

    with open(output_dir / "figure2_extraction_vs_budget.json", "w") as f:
        json.dump(extraction_results, f, indent=2)

    logger.info(f"\nResults saved to {output_dir}")


def _create_synthetic_corpus(path: str, panel):
    """Create a minimal synthetic corpus for testing when real data unavailable."""
    import random
    rng = random.Random(0)
    templates = [
        "def foo():\n    return 42\n",
        "import os\npath = os.getcwd()\n",
        "class Config:\n    debug = False\n",
        "x = [i**2 for i in range(100)]\n",
    ]
    with open(path, "w") as f:
        for i in range(10_000):
            text = rng.choice(templates) * rng.randint(1, 5)
            f.write(json.dumps({"text": text}) + "\n")
        # Append canary documents
        for c in panel:
            f.write(json.dumps({"text": c.full_text}) + "\n")
    logger.info(f"Synthetic corpus written to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="W1: Canary fine-tune evaluation")
    parser.add_argument("--config", default="configs/full_scale.yaml")
    parser.add_argument("--force-retrain", action="store_true",
                        help="Re-train even if checkpoint exists")
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Use synthetic corpus/model when real data absent (testing only)")
    args = parser.parse_args()
    main(args)
