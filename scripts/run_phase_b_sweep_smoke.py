#!/usr/bin/env python3
"""Run CPU-safe B2/B3 decoding sweep smoke tests for W4."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import time
from pathlib import Path

import yaml

from leakcert.canary.generator import CanaryGenerator
from leakcert.defenses.temperature import TemperatureDefense
from leakcert.defenses.top_p import TopPDefense
from leakcert.evaluation.metrics import extraction_hit, rate_summary
from leakcert.evaluation.workloads import W4CodeSecret
from leakcert.model.backend_model import BackendCompletionService


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


def evaluate_service(name: str, service, panel, *, batch_size: int) -> dict:
    workload = W4CodeSecret(panel)
    samples = workload.samples()
    canary_by_id = {c.canary_id: c for c in panel}
    started = time.time()
    completions = service.complete_many(
        [sample.prompt for sample in samples],
        n_samples=1,
        batch_size=batch_size,
    )
    rows = []
    hits = 0
    for sample, result in zip(samples, completions):
        canary = canary_by_id[sample.canary_id]
        text = result[0].text if result else ""
        hit = extraction_hit(canary, text)
        hits += int(hit)
        rows.append(
            {
                "defense": name,
                "prompt_id": sample.prompt_id,
                "canary_id": sample.canary_id,
                "canary_type": getattr(
                    canary.canary_type, "value", str(canary.canary_type)
                ),
                "hit": bool(hit),
            }
        )
    return {
        "summary": rate_summary(hits, len(samples)),
        "duration_sec": time.time() - started,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--temperatures", default="0.2,0.5,1.5")
    parser.add_argument("--top-ps", default="0.5,0.7,0.9")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = cfg["finetune"]["output_dir"]
    base = BackendCompletionService(
        target_path, device=args.device, temperature=1.0, max_new_tokens=64
    )
    panel = make_panel(cfg)

    metadata = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "config": str(Path(args.config).resolve()),
        "target_path": target_path,
        "device": args.device,
        "batch_size": args.batch_size,
        "n_eval": len(panel),
        "temperatures": args.temperatures,
        "top_ps": args.top_ps,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    results = {"metadata": metadata, "b2_temperature": {}, "b3_top_p": {}}
    for temp in [float(x) for x in args.temperatures.split(",") if x.strip()]:
        name = f"B2_temperature_{temp:g}"
        print(f"running {name}", flush=True)
        results["b2_temperature"][name] = evaluate_service(
            name,
            TemperatureDefense(base, temp),
            panel,
            batch_size=args.batch_size,
        )
        (output_dir / "b2_b3_sweep_partial.json").write_text(
            json.dumps(results, indent=2)
        )

    for top_p in [float(x) for x in args.top_ps.split(",") if x.strip()]:
        name = f"B3_top_p_{top_p:g}"
        print(f"running {name}", flush=True)
        results["b3_top_p"][name] = evaluate_service(
            name,
            TopPDefense(base, top_p),
            panel,
            batch_size=args.batch_size,
        )
        (output_dir / "b2_b3_sweep_partial.json").write_text(
            json.dumps(results, indent=2)
        )

    (output_dir / "b2_b3_sweep_summary.json").write_text(json.dumps(results, indent=2))
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "b2": {
                    k: v["summary"]["rate_pct"]
                    for k, v in results["b2_temperature"].items()
                },
                "b3": {
                    k: v["summary"]["rate_pct"] for k, v in results["b3_top_p"].items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
