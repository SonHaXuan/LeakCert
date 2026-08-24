#!/usr/bin/env python3
"""Run CPU-safe missing-evaluation smoke tests for the paper evaluation checklist."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path

import yaml

from leakcert.attacks.a_carlini import ACarlini
from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.defenses.rate_limit import RateLimitDefense
from leakcert.evaluation.metrics import evaluate_pass_at_k, extraction_hit, rate_summary
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W3RealCompletion, W4CodeSecret
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig


def make_panel(cfg: dict):
    n_per_type = cfg["canary"].get("n_eval_per_type", 4)
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
    return panel.stratified_subset(n_per_type)


def summarize_w4_path_a(service, panel, *, batch_size: int) -> dict:
    workload = W4CodeSecret(panel)
    samples = workload.samples()
    canary_by_id = {c.canary_id: c for c in panel}
    completions = service.complete_many(
        [sample.prompt for sample in samples],
        n_samples=1,
        batch_size=batch_size,
    )
    rows = []
    hits = 0
    total = 0
    for sample, result in zip(samples, completions):
        canary = canary_by_id[sample.canary_id]
        completion = result[0].text if result else ""
        hit = extraction_hit(canary, completion)
        hits += int(hit)
        total += 1
        rows.append(
            {
                "prompt_id": sample.prompt_id,
                "canary_id": sample.canary_id,
                "canary_type": getattr(
                    canary.canary_type, "value", str(canary.canary_type)
                ),
                "hit": bool(hit),
                "was_refused": bool(result and result[0].was_refused),
                "refusal_reason": result[0].refusal_reason if result else None,
            }
        )
    return {"summary": rate_summary(hits, total), "rows": rows}


def run_b4(target, panel, *, output_dir: Path, batch_size: int) -> dict:
    no_defense = NoDefense(target)
    b4_soft = RateLimitDefense(target, queries_per_day=10_000)
    b4_strict = RateLimitDefense(target, queries_per_day=32)
    results = {
        "B1_no_defense": summarize_w4_path_a(no_defense, panel, batch_size=batch_size),
        "B4_rate_limit_10000": summarize_w4_path_a(
            b4_soft, panel, batch_size=batch_size
        ),
        "B4_rate_limit_32": summarize_w4_path_a(
            b4_strict, panel, batch_size=batch_size
        ),
    }
    (output_dir / "b4_rate_limit_w4_smoke.json").write_text(
        json.dumps(results, indent=2)
    )
    return results


def run_b7(
    target, ref, panel, *, output_dir: Path, n_samples: int, budget: int
) -> dict:
    attacker = ACarlini(budget=budget, ref_service=ref, n_samples=n_samples)
    started = time.time()
    results = attacker.attack_panel(target, panel)
    hits = sum(int(r.success) for r in results)
    rows = []
    for r in results:
        rows.append(
            {
                "canary_id": r.canary_id,
                "success": bool(r.success),
                "queries_used": r.queries_used,
                "guess": r.guessed_secret,
            }
        )
    summary = {
        "attack": "B7_A_Carlini_smoke",
        "n_samples": n_samples,
        "budget": budget,
        "duration_sec": time.time() - started,
        "summary": rate_summary(hits, len(results)),
        "rows": rows,
    }
    (output_dir / "b7_carlini_smoke.json").write_text(json.dumps(summary, indent=2))
    return summary


def run_w3(
    target,
    ref,
    panel,
    *,
    output_dir: Path,
    max_problems: int,
    runtime_cfg: dict | None = None,
) -> dict:
    workload = W3RealCompletion(multilingual=False)
    samples = workload.samples()[:max_problems]

    class LimitedWorkload:
        def samples(self):
            return samples

    kl = KLEstimator(target, ref)
    runtime_cfg = runtime_cfg or {}
    runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl,
        config=RuntimeConfig(
            query_budget=int(runtime_cfg.get("query_budget", 10_000)),
            refusal_threshold=float(runtime_cfg.get("refusal_threshold", 0.5)),
            use_learned_refusal=bool(runtime_cfg.get("use_learned_refusal", True)),
            use_refusal_heuristics=bool(
                runtime_cfg.get("use_refusal_heuristics", True)
            ),
            target_refusal_rate=float(runtime_cfg.get("target_refusal_rate", 0.01)),
            refusal_model_path=runtime_cfg.get("refusal_model_path"),
            use_suppression=bool(runtime_cfg.get("use_suppression", True)),
            use_canary_hashes=bool(runtime_cfg.get("use_canary_hashes", False)),
            use_accounting=bool(runtime_cfg.get("use_accounting", True)),
            use_rate_limit=bool(runtime_cfg.get("use_rate_limit", True)),
            use_refusal=bool(runtime_cfg.get("use_refusal", True)),
        ),
        panel=panel,
    )
    defenses = {
        "B1_no_defense": NoDefense(target),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(runtime, api_key="phase_a_w3"),
    }
    results = {}
    for name, service in defenses.items():
        started = time.time()
        metrics = evaluate_pass_at_k(
            service,
            LimitedWorkload(),
            k=1,
            n_samples=1,
            timeout=5.0,
        )
        results[name] = {
            "duration_sec": time.time() - started,
            "n_problems": metrics.n_problems,
            "pass_at_1": metrics.pass_at_1,
            "pass_at_1_pct": round(metrics.pass_at_1 * 100.0, 2),
            "n_correct_at_1": metrics.n_correct_at_1,
        }
        if name == "LEAKCERT":
            results[name]["refusal_rate_pct"] = round(runtime.refusal_rate() * 100.0, 2)
            results[name]["latency"] = runtime.latency_stats()
    (output_dir / "w3_utility_refusal_latency_smoke.json").write_text(
        json.dumps(results, indent=2)
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--b7-samples", type=int, default=4)
    parser.add_argument("--b7-budget", type=int, default=64)
    parser.add_argument("--w3-problems", type=int, default=5)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    target_path = cfg["finetune"]["output_dir"]
    model_name = cfg["model"].get(
        "target_model_small", cfg["model"].get("target_model")
    )
    target = BackendCompletionService(
        target_path,
        device=args.device,
        temperature=1.0,
        max_new_tokens=64,
    )
    ref = BackendCompletionService(
        model_name,
        device=args.device,
        temperature=1.0,
        max_new_tokens=64,
    )
    panel = make_panel(cfg)

    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": str(Path(args.config).resolve()),
        "device": args.device,
        "target_path": target_path,
        "ref_model": model_name,
        "n_eval": len(panel),
        "batch_size": args.batch_size,
        "b7_samples": args.b7_samples,
        "b7_budget": args.b7_budget,
        "w3_problems": args.w3_problems,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    summary = {
        "metadata": metadata,
        "b4": run_b4(target, panel, output_dir=output_dir, batch_size=args.batch_size),
        "b7": run_b7(
            target,
            ref,
            panel,
            output_dir=output_dir,
            n_samples=args.b7_samples,
            budget=args.b7_budget,
        ),
        "w3": run_w3(
            target,
            ref,
            panel,
            output_dir=output_dir,
            max_problems=args.w3_problems,
            runtime_cfg=cfg.get("runtime", {}),
        ),
    }
    summary["duration_sec"] = time.time() - started
    (output_dir / "phase_a_smoke_summary.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "duration_sec": summary["duration_sec"],
                "b4_keys": list(summary["b4"]),
                "b7_rate_pct": summary["b7"]["summary"]["rate_pct"],
                "w3_defenses": list(summary["w3"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
