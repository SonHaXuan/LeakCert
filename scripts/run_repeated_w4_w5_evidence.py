#!/usr/bin/env python3
"""Run repeated W4/W5 extraction evidence on the current canary panel."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from collections import defaultdict
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.certificate.kl_estimator import KLEstimator
from leakcert.defenses.content_filter import ContentFilterDefense
from leakcert.defenses.no_defense import NoDefense
from leakcert.evaluation.metrics import extraction_hit, rate_summary
from leakcert.evaluation.runner import _RuntimeServiceAdapter
from leakcert.evaluation.workloads import W4CodeSecret, W5Paraphrase
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


def evaluate_workload(name: str, service, workload, panel, repeats: int, batch_size: int) -> dict:
    samples = workload.samples()
    canary_by_id = {c.canary_id: c for c in panel}
    aggregate = [0, 0]
    per_repeat = []
    per_type = defaultdict(lambda: [0, 0])
    per_mode = defaultdict(lambda: [0, 0])
    audit_rows = []
    started = time.time()
    prompts = [sample.prompt for sample in samples]
    for repeat in range(repeats):
        completions = service.complete_many(prompts, n_samples=1, batch_size=batch_size)
        hits = 0
        total = 0
        for sample, result in zip(samples, completions):
            canary = canary_by_id[sample.canary_id]
            text = result[0].text if result else ""
            hit = extraction_hit(canary, text)
            hits += int(hit)
            total += 1
            ctype = getattr(canary.canary_type, "value", str(canary.canary_type))
            mode = sample.paraphrase_mode or "direct"
            per_type[ctype][0] += int(hit)
            per_type[ctype][1] += 1
            per_mode[mode][0] += int(hit)
            per_mode[mode][1] += 1
            audit_rows.append({
                "repeat": repeat,
                "defense": name,
                "workload": workload.name,
                "prompt_id": sample.prompt_id,
                "canary_id": sample.canary_id,
                "canary_type": ctype,
                "paraphrase_mode": sample.paraphrase_mode,
                "hit": bool(hit),
            })
        aggregate[0] += hits
        aggregate[1] += total
        per_repeat.append({"repeat": repeat, **rate_summary(hits, total)})
    return {
        "duration_sec": time.time() - started,
        "summary": rate_summary(aggregate[0], aggregate[1]),
        "per_repeat": per_repeat,
        "per_type": {k: rate_summary(v[0], v[1]) for k, v in sorted(per_type.items())},
        "per_mode": {k: rate_summary(v[0], v[1]) for k, v in sorted(per_mode.items())},
        "audit_rows": audit_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = cfg["finetune"]["output_dir"]
    model_name = cfg["model"].get("target_model_small", cfg["model"].get("target_model"))
    target = BackendCompletionService(
        target_path,
        device=args.device,
        temperature=1.0,
        max_new_tokens=args.max_new_tokens,
    )
    ref = BackendCompletionService(
        model_name,
        device=args.device,
        temperature=1.0,
        max_new_tokens=args.max_new_tokens,
    )
    panel = make_panel(cfg)
    kl = KLEstimator(target, ref)
    runtime = LeakCertRuntime(
        service=target,
        kl_estimator=kl,
        config=RuntimeConfig(query_budget=cfg.get("evaluation", {}).get("query_budget", 100)),
        panel=panel,
    )
    defenses = {
        "B1_no_defense": NoDefense(target),
        "B5_content_filter": ContentFilterDefense(target),
        "LEAKCERT": _RuntimeServiceAdapter(runtime, api_key="repeated_evidence"),
    }
    workloads = {
        "W4": W4CodeSecret(panel),
        "W5": W5Paraphrase(W4CodeSecret(panel)),
    }
    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": str(Path(args.config).resolve()),
        "target_path": target_path,
        "ref_model": model_name,
        "device": args.device,
        "repeats": args.repeats,
        "batch_size": args.batch_size,
        "max_new_tokens": args.max_new_tokens,
        "n_eval": len(panel),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    summary = {"metadata": metadata, "results": {}}
    audit_path = output_dir / "audit_rows.jsonl"
    with audit_path.open("w") as audit:
        for defense_name, service in defenses.items():
            summary["results"][defense_name] = {}
            for workload_name, workload in workloads.items():
                print(f"running {defense_name} {workload_name}", flush=True)
                result = evaluate_workload(
                    defense_name,
                    service,
                    workload,
                    panel,
                    repeats=args.repeats,
                    batch_size=args.batch_size,
                )
                for row in result.pop("audit_rows"):
                    audit.write(json.dumps(row) + "\n")
                summary["results"][defense_name][workload_name] = result
                (output_dir / "repeated_w4_w5_partial.json").write_text(json.dumps(summary, indent=2))
    (output_dir / "repeated_w4_w5_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({
        "output_dir": str(output_dir),
        "rates": {
            d: {w: r["summary"]["rate_pct"] for w, r in ws.items()}
            for d, ws in summary["results"].items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
