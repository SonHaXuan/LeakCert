#!/usr/bin/env python3
"""Run a focused W3 utility diagnostic on B1/B5/LEAKCERT.

This is intended to answer whether low W3 utility is caused by the target
checkpoint itself or by the LEAKCERT runtime/refusal layer.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.evaluation.metrics import evaluate_pass_at_k
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W3RealCompletion
from leakcert.model.backend_model import BackendCompletionService
from leakcert.runtime.leakcert_runtime import LeakCertRuntime, RuntimeConfig


def make_panel(cfg: dict):
    canary_cfg = cfg.get("canary", {})
    n_per_type = int(canary_cfg.get("n_eval_per_type", 8))
    gen = CanaryGenerator(
        n_canaries=int(canary_cfg.get("n_canaries", 64)),
        n_eval=n_per_type * 4,
        seed=int(canary_cfg.get("seed", cfg.get("seed", 0))),
    )
    panel = gen.generate_panel(
        include_paraphrase=bool(canary_cfg.get("include_paraphrase", True)),
        n_t3=n_per_type,
        n_t4=n_per_type,
    )
    return panel.stratified_subset(n_per_type)


def limited_w3(cfg: dict, max_problems: int):
    corpus = cfg.get("corpus", {})
    workload = W3RealCompletion(
        data_path=corpus.get("utility_eval_path") or None,
        subset=corpus.get("utility_subset", "utility_eval"),
        multilingual=bool(corpus.get("utility_multilingual", False)),
    )
    samples = workload.samples()[:max_problems]

    class LimitedWorkload:
        def samples(self):
            return samples

    return LimitedWorkload(), len(samples)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-problems", type=int, default=164)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    started = time.time()
    cfg_path = Path(args.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text())
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "configs").mkdir(exist_ok=True)
    shutil.copy2(cfg_path, out / "configs" / cfg_path.name)

    model_cfg = cfg.get("model", {})
    target_path = cfg["finetune"]["output_dir"]
    ref_name = (
        model_cfg.get("ref_model")
        or model_cfg.get("target_model_small")
        or model_cfg.get("target_model")
    )
    device = model_cfg.get("device", "auto")
    max_new_tokens = int(model_cfg.get("max_new_tokens", 16))
    temperature = float(model_cfg.get("temperature", 0.0))
    top_p = float(model_cfg.get("top_p", 1.0))

    target = BackendCompletionService(
        target_path,
        device=device,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=max_new_tokens,
    )
    ref = BackendCompletionService(
        ref_name,
        device=device,
        temperature=temperature,
        top_p=top_p,
        max_new_tokens=max_new_tokens,
    )
    workload, n_problems = limited_w3(cfg, args.max_problems)
    panel = make_panel(cfg)
    runtime_cfg = cfg.get("runtime", {})
    runtime = LeakCertRuntime(
        service=target,
        kl_estimator=KLEstimator(target, ref),
        config=RuntimeConfig(
            query_budget=int(
                runtime_cfg.get(
                    "query_budget", cfg.get("evaluation", {}).get("query_budget", 200)
                )
            ),
            refusal_threshold=float(runtime_cfg.get("refusal_threshold", 0.95)),
            target_refusal_rate=float(runtime_cfg.get("target_refusal_rate", 0.02)),
            refusal_model_path=runtime_cfg.get("refusal_model_path"),
            use_learned_refusal=bool(runtime_cfg.get("use_learned_refusal", True)),
            use_refusal_heuristics=bool(
                runtime_cfg.get("use_refusal_heuristics", False)
            ),
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
        "LEAKCERT": _RuntimeServiceAdapter(runtime, api_key="w3_diagnostic"),
    }
    rows = {}
    for name, service in defenses.items():
        t0 = time.time()
        metrics = evaluate_pass_at_k(
            service,
            workload,
            k=1,
            n_samples=1,
            timeout=args.timeout,
        )
        row = {
            "duration_sec": time.time() - t0,
            "n_problems": metrics.n_problems,
            "n_correct_at_1": metrics.n_correct_at_1,
            "pass_at_1_pct": round(metrics.pass_at_1 * 100.0, 2),
        }
        if name == "LEAKCERT":
            row["refusal_rate_pct"] = round(runtime.refusal_rate() * 100.0, 2)
            row["latency"] = runtime.latency_stats()
        rows[name] = row
        print(json.dumps({"defense": name, **row}, indent=2), flush=True)

    summary = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "hostname": socket.gethostname(),
            "python": platform.python_version(),
            "config": str(cfg_path),
            "target_path": target_path,
            "ref_name": ref_name,
            "device": device,
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "max_problems": args.max_problems,
            "n_loaded_problems": n_problems,
            "duration_sec": time.time() - started,
        },
        "rows": rows,
    }
    (out / "w3_utility_diagnostic.json").write_text(json.dumps(summary, indent=2))
    md = [
        "# W3 Utility Diagnostic",
        "",
        f"Generated: `{summary['metadata']['timestamp']}`",
        "",
        "| defense | pass@1 | correct/problems | refusal |",
        "|---|---:|---:|---:|",
    ]
    for name, row in rows.items():
        md.append(
            f"| {name} | {row['pass_at_1_pct']:.2f}% | "
            f"{row['n_correct_at_1']}/{row['n_problems']} | "
            f"{row.get('refusal_rate_pct', 0.0):.2f}% |"
        )
    (out / "w3_utility_diagnostic.md").write_text("\n".join(md) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
