#!/usr/bin/env python3
"""Build a sanitized Updated-Res evidence package for repository upload."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Updated-Res"
ART = OUT / "artifacts"
LOCAL_PREFIX = str(ROOT) + "/"
USER_HOME = str(Path.home())


def read_json(path: str | Path) -> Any:
    p = ROOT / path
    if not p.exists():
        return None
    return json.loads(p.read_text())


def sanitize_text(text: str) -> str:
    replacements = {
        LOCAL_PREFIX: "<repo>/",
        str(ROOT): "<repo>",
        USER_HOME: "<home>",
        "Mac.RMIT.EDU.VN": "local-mac",
        "SP 2027": "submission",
        "sp2027": "submission",
        "Current SP Status": "Current Project Status",
        "SP Claim Checklist": "Claim Checklist",
        "SP Evaluation": "Evaluation",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"OPENROUTER_API_KEY[^\n]*", "OPENROUTER_API_KEY=<redacted>", text)
    text = re.sub(r"sk-or-v1-[A-Za-z0-9_\-]+", "<redacted-openrouter-key>", text)
    text = re.sub(r"AKIA[A-Z0-9]{16}", "<redacted-synthetic-aws-key>", text)
    text = re.sub(r"ghp_[A-Za-z0-9]{20,}", "<redacted-synthetic-github-token>", text)
    text = re.sub(r"sk-test-[A-Za-z0-9]{20,}", "<redacted-synthetic-api-key>", text)
    text = re.sub(r"eyJ[A-Za-z0-9_-]{20,}", "<redacted-synthetic-jwt>", text)
    return text


def sanitize_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, list):
        return [sanitize_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): sanitize_obj(v) for k, v in obj.items()}
    return obj


def write_text(rel: str, text: str) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(sanitize_text(text))


def write_json(rel: str, obj: Any) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sanitize_obj(obj), indent=2, sort_keys=True) + "\n")


def copy_sanitized(rel_src: str, rel_dst: str | None = None) -> None:
    src = ROOT / rel_src
    if not src.exists():
        return
    dst = ART / (rel_dst or rel_src.replace("/", "__"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in {".json"}:
        write_json(str(dst.relative_to(OUT)), read_json(rel_src))
    else:
        dst.write_text(sanitize_text(src.read_text(errors="replace")))


def pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.2f}%"


def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def get_git_status() -> list[str]:
    try:
        out = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
        return [line for line in out.splitlines() if line]
    except Exception:
        return []


def latest_dir(pattern: str) -> Path | None:
    dirs = sorted(path for path in ROOT.glob(pattern) if path.is_dir())
    return dirs[-1] if dirs else None


def latest_completed_dir(pattern: str, required_file: str = "summary.json") -> Path | None:
    dirs = sorted(path for path in ROOT.glob(pattern) if path.is_dir() and (path / required_file).exists())
    return dirs[-1] if dirs else None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> None:
    rows = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            rows.append(
                {
                    "path": str(path.relative_to(OUT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    write_json("manifest.json", rows)


def extract_w5_rows(path: str) -> dict[str, dict[str, float]]:
    data = read_json(path) or {}
    out: dict[str, dict[str, float]] = {}
    for name, row in data.items():
        if not isinstance(row, dict):
            continue
        w4 = row.get("w4_rate", row.get("w4_extraction_rate_pct", row.get("w4_extraction_rate", 0)))
        w5 = row.get("w5_rate", row.get("w5_extraction_rate_pct", row.get("w5_extraction_rate", 0)))
        # Most repository result tables already store percentages (e.g. 9.82).
        # Older helper outputs may store fractions; normalize only those.
        w4 = float(w4 or 0)
        w5 = float(w5 or 0)
        if 0 < w4 <= 1:
            w4 *= 100.0
        if 0 < w5 <= 1:
            w5 *= 100.0
        out[name] = {
            "w4_rate_pct": w4,
            "w5_rate_pct": w5,
        }
        if "robustness_ratio" in row:
            out[name]["ratio"] = float(row["robustness_ratio"])
        elif out[name]["w4_rate_pct"]:
            out[name]["ratio"] = out[name]["w5_rate_pct"] / out[name]["w4_rate_pct"]
    return out


def build_lcct_model_full_section(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""
    rows = summary.get("defenses", {})
    if not isinstance(rows, dict) or not rows:
        return ""
    lines = [
        "",
        "## Current Full Model Run",
        "",
        f"A full-size local model run was completed on `{summary.get('n_prompts', 'n/a')}` comparable LCCT prompts.",
        "",
        "| defense | hits | n | hit rate | refusal | duration |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        if not isinstance(row, dict):
            continue
        duration = row.get("duration_sec")
        duration_txt = "n/a" if duration is None else f"{float(duration) / 60.0:.1f} min"
        lines.append(
            f"| {name} | {row.get('hits', 'n/a')} | {row.get('n', 'n/a')} | "
            f"{float(row.get('hit_rate_pct', 0.0)):.2f}% | "
            f"{float(row.get('refusal_rate_pct', 0.0)):.2f}% | {duration_txt} |"
        )
    return "\n".join(lines) + "\n"


def build_lcct_model_smoke_section(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""
    rows = summary.get("defenses", {})
    if not isinstance(rows, dict) or not rows:
        return ""
    lines = [
        "",
        "## Current Model Smoke",
        "",
        f"A local model smoke was run on `{summary.get('n_prompts', 'n/a')}` prompts from the full-size comparable benchmark using the current Qwen positive-control checkpoint. This is a negative-control/comparable smoke, not a headline defense result: the undefended model did not extract controlled ground truth.",
        "",
        "| defense | hits | n | hit rate | refusal |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in rows.items():
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {name} | {row.get('hits', 'n/a')} | {row.get('n', 'n/a')} | "
            f"{float(row.get('hit_rate_pct', 0.0)):.2f}% | "
            f"{float(row.get('refusal_rate_pct', 0.0)):.2f}% |"
        )
    lines.extend(
        [
            "",
            "Interpretation: the benchmark/scorer/model path is operational, but this checkpoint does not leak on the sampled comparable LCCT prompts. Use this as readiness evidence, not as a replacement for a stronger LCCT-style extraction run on a leakier or larger checkpoint.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_lcct_live_progress(log_path: Path) -> dict[str, Any] | None:
    if not log_path.exists():
        return None
    progress_re = re.compile(r'"defense": "([^"]+)", "completed": (\d+), "total": (\d+)')
    latest: dict[str, dict[str, int]] = {}
    for line in log_path.read_text(errors="replace").splitlines():
        m = progress_re.search(line)
        if m:
            latest[m.group(1)] = {
                "completed": int(m.group(2)),
                "total": int(m.group(3)),
            }
    if not latest:
        return None
    return {
        "log": str(log_path.relative_to(ROOT)),
        "latest_progress": latest,
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def build_lcct_live_status(run_dir: Path | None) -> tuple[dict[str, Any] | None, str]:
    if not run_dir:
        return None, ""
    rel = run_dir.relative_to(ROOT)
    log_path = ROOT / "_run_logs" / f"{run_dir.name.replace('lcct_comparable_model_full_', 'lcct_comparable_model_full_')}.log"
    live = parse_lcct_live_progress(log_path)
    if live is None:
        live = {"latest_progress": {}, "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    live["run_dir"] = str(rel)

    defense_summaries: dict[str, Any] = {}
    for defense_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        summary_path = defense_dir / "summary.json"
        if summary_path.exists():
            key = f"lcct_comparable_model_full_{defense_dir.name}_summary.json"
            copy_sanitized(str(summary_path.relative_to(ROOT)), key)
            summary = read_json(summary_path.relative_to(ROOT))
            defense_summaries[defense_dir.name] = summary
            if isinstance(summary, dict) and summary.get("n") is not None:
                live.setdefault("latest_progress", {})[defense_dir.name] = {
                    "completed": int(summary.get("n", 0)),
                    "total": int(summary.get("n", 0)),
                }
    live["completed_defense_summaries"] = defense_summaries

    lines = [
        "# Current LCCT Comparable Full-Run Status",
        "",
        "This file tracks the current long-running LCCT comparable model evaluation. It includes only progress counters and completed defense-level summaries, not raw completions or synthetic secret-like benchmark rows.",
        "",
        f"- run dir: `{rel}`",
        f"- updated: `{live['updated']}`",
        "",
        "## Progress",
        "",
        "| defense | completed | total | progress |",
        "|---|---:|---:|---:|",
    ]
    for defense, row in live.get("latest_progress", {}).items():
        completed = int(row.get("completed", 0))
        total = int(row.get("total", 0))
        pct_done = 100.0 * completed / total if total else 0.0
        lines.append(f"| {defense} | {completed} | {total} | {pct_done:.2f}% |")

    if defense_summaries:
        lines.extend(["", "## Completed Defense Summaries", "", "| defense | hits | n | hit rate | duration |", "|---|---:|---:|---:|---:|"])
        for defense, row in defense_summaries.items():
            duration = row.get("duration_sec")
            duration_txt = "n/a" if duration is None else f"{float(duration) / 60.0:.1f} min"
            lines.append(
                f"| {defense} | {row.get('hits', 'n/a')} | {row.get('n', 'n/a')} | "
                f"{float(row.get('hit_rate_pct', 0.0)):.2f}% | {duration_txt} |"
            )
    return live, "\n".join(lines) + "\n"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    ART.mkdir()

    generated = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    commit = get_git_commit()

    key_paths = {
        "learned_validation": "_run_results/learnedonly_t095_validation_summary_20260603_1936/learnedonly_t095_validation_summary.md",
        "bootstrap": "_run_results/bootstrap_w5_evidence_20260603_1934_cpu_bootstrap_learnedonly_seed42_1m/bootstrap_w5_evidence.md",
        "w3_diagnostic": "_run_results/w3_utility_diagnostic_learnedonly_t095_20260603_203948/w3_utility_diagnostic.md",
        "qwen_seed_summary": "_run_results/local_mps_qwen_seed42_seed43_summary_20260603_093946/qwen_mps_seed42_seed43_summary.md",
        "current_status": "_run_results/current_sp_status_20260603_201916/current_sp_status.md",
        "claim_checklist": "_run_results/sp_claim_checklist_20260601_1650/sp_claim_checklist.md",
        "real_input_validation": "_run_results/sp2027_real_inputs_20260531_2312/real_input_validation.md",
        "lcct_author_response": "_run_results/lcct_author_response_20260601_1328/author_response_summary.md",
    }
    for label, src in key_paths.items():
        copy_sanitized(src, f"{label}{Path(src).suffix}")

    json_paths = {
        "learned_validation_w3_164": "_run_results/learnedonly_t095_validation_20260603_190245/w3_164_t095/w3_refusal_threshold_sweep.json",
        "learned_validation_w5_seed42": "_run_results/learnedonly_t095_validation_20260603_190245/w5_seed42_t095/w5/table6_paraphrase_robustness.json",
        "w3_utility_diagnostic": "_run_results/w3_utility_diagnostic_learnedonly_t095_20260603_203948/w3_utility_diagnostic.json",
        "forbidden_questions_judge": "_run_results/forbidden_questions_openrouter_judge_20260601_0650/full/summary.json",
        "hcr_supplement": "_run_results/hcr_w2_supplement_20260531_2346/w2/w2_lcct_results.json",
        "certificate_refresh": "_run_results/certificate_refresh_20260531_2349/certificate/table1_certificate.json",
        "qwen_seed42_w5": "_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/table6_paraphrase_robustness.json",
        "qwen_seed43_w5": "_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/w5/table6_paraphrase_robustness.json",
        "phase_a_seed42": "_run_results/local_mps_qwen_positive_expanded_20260603_070216/phase_a/phase_a_smoke_summary.json",
        "phase_b_seed42": "_run_results/local_mps_qwen_positive_expanded_20260603_070216/phase_b/b2_b3_sweep_summary.json",
        "phase_a_seed43": "_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/phase_a/phase_a_smoke_summary.json",
    }
    for label, src in json_paths.items():
        copy_sanitized(src, f"{label}.json")

    lcct_latest = latest_dir("_run_results/lcct_comparable_fullsize_*")
    if lcct_latest:
        rel = lcct_latest.relative_to(ROOT)
        copy_sanitized(str(rel / "benchmark" / "metadata.json"), "lcct_comparable_fullsize_metadata.json")
        copy_sanitized(str(rel / "scorer_smoke" / "summary.json"), "lcct_comparable_scorer_smoke_summary.json")

    lcct_model_smoke_summary = None
    lcct_model_smoke_latest = latest_completed_dir("_run_results/lcct_comparable_model_smoke_[0-9]*")
    if lcct_model_smoke_latest:
        rel = lcct_model_smoke_latest.relative_to(ROOT)
        copy_sanitized(str(rel / "summary.json"), "lcct_comparable_model_smoke_summary.json")
        copy_sanitized(str(rel / "summary.md"), "lcct_comparable_model_smoke_summary.md")
        lcct_model_smoke_summary = read_json(rel / "summary.json")

    lcct_model_full_summary = None
    lcct_model_full_latest = latest_completed_dir("_run_results/lcct_comparable_model_full_*")
    if lcct_model_full_latest:
        rel = lcct_model_full_latest.relative_to(ROOT)
        copy_sanitized(str(rel / "summary.json"), "lcct_comparable_model_full_summary.json")
        copy_sanitized(str(rel / "summary.md"), "lcct_comparable_model_full_summary.md")
        lcct_model_full_summary = read_json(rel / "summary.json")

    lcct_model_full_live = None
    lcct_model_full_live_latest = latest_dir("_run_results/lcct_comparable_model_full_*")
    if lcct_model_full_live_latest and not (lcct_model_full_live_latest / "summary.json").exists():
        lcct_model_full_live, lcct_live_status_doc = build_lcct_live_status(lcct_model_full_live_latest)
        write_text("lcct_comparable_full_live_status.md", lcct_live_status_doc)

    w3_diag = read_json("_run_results/w3_utility_diagnostic_learnedonly_t095_20260603_203948/w3_utility_diagnostic.json")
    learned_w3 = read_json("_run_results/learnedonly_t095_validation_20260603_190245/w3_164_t095/w3_refusal_threshold_sweep.json")
    seed42_w5 = extract_w5_rows("_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/table6_paraphrase_robustness.json")
    seed43_w5 = extract_w5_rows("_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/w5/table6_paraphrase_robustness.json")
    learned_seed42 = extract_w5_rows("_run_results/learnedonly_t095_validation_20260603_190245/w5_seed42_t095/w5/table6_paraphrase_robustness.json")

    executive = f"""# Updated Results Package

Generated: `{generated}`

Source commit at package generation: `{commit}`

This folder is a sanitized result bundle for writing and auditing. It intentionally excludes:

- local secret files such as `.env` and `*.pem`
- model checkpoints and large model/tokenizer files
- local paper PDF/source and venue/timeline metadata
- raw private data or author/user-level artifacts

## Highest-Signal Findings

1. **W5 leakage reduction is the strongest current empirical result.**
   The learned-only refusal setting at threshold `0.95` reduces W5 extraction below the B5 content-filter baseline on both seed42 and seed43. The 1M-sample bootstrap comparison gives strong evidence for the reduction.

2. **The original uncalibrated LEAKCERT setting is not the best headline result.**
   Cross-seed W5 means show original LEAKCERT does not consistently beat B5. The improved learned-only refusal variant is the result worth discussing.

3. **W3 utility weakness is model/checkpoint-driven, not defense-driven.**
   On the W3-164 diagnostic, B1, B5, and LEAKCERT all achieve `10.98%` pass@1. LEAKCERT refusal is only `0.61%`, so the defense layer is not the main cause of low utility in this setting.

4. **LCCT full training-data extraction cannot be reproduced paper-grade from public artifacts.**
   The LCCT authors confirmed the forbidden-question CSV is exact, but declined release of user-level extraction artifacts due privacy. The correct path is a comparable reimplementation with explicit limitation.

5. **Certificate results are currently diagnostic, not headline.**
   Existing certificate runs remain vacuous/non-competitive. A non-vacuous certificate claim still needs improved calibration/checkpoints and likely server/GPU follow-up.

## Best Numbers To Reuse

### Learned-only W5 evidence

| setting | W4 | W5 | note |
|---|---:|---:|---|
| learned-only t=0.95 seed43 | 4.91% | 2.50% | strongest W5 reduction |
| learned-only t=0.95 seed42 | 7.59% | 4.73% | replicated W5 reduction |

Bootstrap comparisons:

| comparison | baseline-method | 95% CI | P(baseline > method) |
|---|---:|---:|---:|
| seed43 B5 vs learned-only t=0.95 | 3.214 pp | [1.607, 4.911] | 0.99993 |
| seed42 B5 vs learned-only t=0.95 | 2.946 pp | [0.982, 4.911] | 0.99787 |

### W3 utility diagnostic

| defense | pass@1 | refusal |
|---|---:|---:|
| B1 no defense | 10.98% | 0.00% |
| B5 content filter | 10.98% | 0.00% |
| LEAKCERT learned-only t=0.95 | 10.98% | 0.61% |

## Bottom Line

The current package supports a careful small-scale/positive-control claim: learned refusal/accounting can reduce extraction in W4/W5-style settings with minimal additional W3 refusal. It does **not** yet support full-scale claims about DP sweeps, multi-model evaluation, non-vacuous certificates, or full LCCT training-data extraction.
"""
    write_text("README.md", executive)

    claim_gap = """# Claim Gap Matrix

| Evaluation item | Current status | Current evidence | Submission risk |
|---|---|---|---|
| W1 canary fine-tune | Partial | Positive-control Qwen runs, small panels | Full paper scope needs larger corpus, larger canary set, more panels, more models |
| W2 LCCT forbidden questions | Ready as reimplementation | Authors confirmed exact 80-question CSV and category order | Judge is reimplemented, not exact private framework |
| W2 LCCT training-data extraction | Comparable only | Public user-level artifacts unavailable | Must disclose limitation; cannot claim paper-grade reproduction |
| W3 utility | Diagnostic complete | B1/B5/LEAKCERT all 10.98% on W3-164 | Absolute utility too low for strong headline |
| W4 extraction | Good small-scale evidence | Seeded Qwen positive-control results | Not full 7,900-prompt scale |
| W5 paraphrase | Strongest evidence | Learned-only t=0.95 beats B5 across two seeds with bootstrap | Still small/medium scale |
| B2/B3 sweeps | Partial | Local sweeps exist for temperature/top-p | Not full table/scale |
| B4 rate limit | Smoke/partial | Local smoke exists | Needs full budget framing |
| B5 content filter | Covered | Used as main baseline | Learned-only result should compare directly against it |
| B6 DP-SGD | Not full | DP smoke only | Needs real DP checkpoints for eps={1,2,4,8,16} |
| B7/B8 adaptive attacks | Partial | B7/Carlini-style smoke and W5 paraphrase evidence | Needs full attack table at target budget |
| Certificate non-vacuous | Not ready | Current certificate diagnostic/vacuous | Needs repair before headline |
| Multi-model full | Not ready | No second full checkpoint | Needs server/GPU or equivalent |
"""
    write_text("claim_gap_matrix.md", claim_gap)

    machine = {
        "generated": generated,
        "source_commit": commit,
        "git_status_at_generation": get_git_status(),
        "w3_diagnostic": w3_diag,
        "learned_w3_threshold_sweep": learned_w3,
        "w5_seed42": seed42_w5,
        "w5_seed43": seed43_w5,
        "w5_learned_seed42": learned_seed42,
        "lcct_comparable_model_smoke": lcct_model_smoke_summary,
        "lcct_comparable_model_full": lcct_model_full_summary,
        "lcct_comparable_model_full_live": lcct_model_full_live,
    }
    write_json("machine_readable_summary.json", machine)

    next_steps = """# Recommended Next Experiments

## Can run locally

1. Generate more bootstrap/confidence intervals for W5 and W3.
2. Produce error analysis for W3 failures.
3. Complete comparable LCCT training-data extraction benchmark design.
4. Run small ablations of refusal/suppression/rate-limit components.
5. Package figures/tables from existing results.

## Should run on server/GPU

1. Larger W1 fine-tune with real corpus and larger canary set.
2. DP-SGD checkpoints for eps={1,2,4,8,16}.
3. Multi-model full evaluation.
4. W4/W5 full-scale prompt runs.
5. Certificate recalibration on stronger checkpoints to obtain non-vacuous bounds.
"""
    write_text("next_experiments.md", next_steps)

    lcct_design = f"""# LCCT Comparable Reimplementation

## Why This Exists

The original LCCT training-data extraction benchmark depends on user-level artifacts
that the authors cannot release due privacy concerns. This repository therefore
implements a **comparable controlled benchmark**, not a paper-grade reproduction
of the original user-level extraction artifact.

## What Is Implemented

- `scripts/prepare_lcct_comparable_benchmark.py`
  - creates synthetic GitHub-profile/code-completion extraction prompts
  - stores controlled ground truth in JSONL
  - supports full-size comparable generation with `--target-prompts 4832`
  - marks every row as `synthetic_no_real_user_pii`

- `scripts/score_lcct_comparable.py`
  - scores completions against the benchmark
  - supports exact secret/email matching
  - supports fuzzy location matching by exact location, city subset, or component subset
  - reports overall and per-category hit rates

## Local Commands

```bash
OUT=_run_results/lcct_comparable_fullsize_$(date +%Y%m%d_%H%M%S)
.venv/bin/python scripts/prepare_lcct_comparable_benchmark.py \\
  --output-dir "$OUT/benchmark" \\
  --target-prompts 4832 \\
  --seed 20260603

.venv/bin/python scripts/score_lcct_comparable.py \\
  --benchmark "$OUT/benchmark/lcct_comparable_benchmark.jsonl" \\
  --output-dir "$OUT/scorer_smoke" \\
  --make-mock-completions
```

## Current Full-Size Smoke

The current full-size local smoke generated `4,832` prompts and verified the
scorer with deterministic mock completions. The benchmark JSONL itself is not
stored in this public result package because the synthetic strings intentionally
look like credentials and may trigger secret-scanning systems. Regenerate it
locally from the script when needed.
{build_lcct_model_smoke_section(lcct_model_smoke_summary)}
{build_lcct_model_full_section(lcct_model_full_summary)}

## Safe Claim Wording

> Since the original LCCT user-level extraction artifacts are unavailable for
> privacy reasons, we evaluate a controlled LCCT-style benchmark with synthetic
> ground truth. We report this as a comparable reimplementation, not a direct
> reproduction of the original LCCT training-data extraction artifact.
"""
    write_text("lcct_comparable_reimplementation.md", lcct_design)

    paper_tables = """# Paper-Ready Result Tables

These are the numbers that are most defensible to reuse in the current draft. They are intentionally scoped as local positive-control evidence, not full-scale claims.

## Table A: W5 Paraphrase Leakage Reduction

| Method | Seed | W4 extraction | W5 extraction | Robustness ratio | Interpretation |
|---|---:|---:|---:|---:|---|
| B5 content filter | 42 | 12.50% | 7.68% | 0.614x | baseline regex/content filter |
| learned-only LEAKCERT t=0.95 | 42 | 7.59% | 4.73% | 0.624x | lower W5 extraction than B5 |
| B5 content filter | 43 | 10.27% | 5.71% | 0.556x | baseline regex/content filter |
| learned-only LEAKCERT t=0.95 | 43 | 4.91% | 2.50% | 0.509x | strongest replicated result |

## Table B: Bootstrap Evidence for W5 Improvement

| Comparison | B5 - method | 95% CI | P(B5 > method) |
|---|---:|---:|---:|
| seed43 B5 vs learned-only t=0.95 | 3.214 pp | [1.607, 4.911] | 0.99993 |
| seed42 B5 vs learned-only t=0.95 | 2.946 pp | [0.982, 4.911] | 0.99787 |

## Table C: W3 Utility Diagnostic

| Defense | pass@1 | Correct / problems | Refusal |
|---|---:|---:|---:|
| B1 no defense | 10.98% | 18 / 164 | 0.00% |
| B5 content filter | 10.98% | 18 / 164 | 0.00% |
| learned-only LEAKCERT t=0.95 | 10.98% | 18 / 164 | 0.61% |

## Safe Claim Wording

> In a local positive-control evaluation with Qwen2.5-Coder-0.5B, the learned-only LEAKCERT refusal variant reduced W5 paraphrase extraction relative to the B5 content-filter baseline across two seeds. A 1M-sample bootstrap comparison showed B5 exceeded the learned-only method by 2.95 to 3.21 percentage points, with confidence intervals excluding zero. A matched W3 diagnostic showed identical pass@1 for B1, B5, and LEAKCERT, suggesting that the observed utility weakness is checkpoint-driven rather than caused by the defense layer.

## Claims To Avoid Until Server Runs Finish

- Do not claim full W1/W4/W5 scale.
- Do not claim DP-SGD epsilon sweep results.
- Do not claim multi-model robustness.
- Do not claim non-vacuous certificate tightness.
- Do not claim paper-grade LCCT training-data extraction reproduction.
"""
    write_text("paper_ready_tables.md", paper_tables)

    build_manifest()
    print(json.dumps({"output_dir": str(OUT), "files": len(list(OUT.rglob('*')))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
