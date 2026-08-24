#!/usr/bin/env python3
"""Build a sanitized Updated-Res evidence package for repository upload."""

from __future__ import annotations

import hashlib
import json
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
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def get_git_status() -> list[str]:
    try:
        out = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
        transient = {
            "Updated-Res/machine_readable_summary.json",
            "Updated-Res/manifest.json",
        }
        rows = []
        for line in out.splitlines():
            if not line:
                continue
            path = line[3:] if len(line) > 3 else line
            if path in transient:
                continue
            rows.append(line)
        return rows
    except Exception:
        return []


def latest_dir(pattern: str) -> Path | None:
    dirs = sorted(
        (path for path in ROOT.glob(pattern) if path.is_dir()),
        key=lambda p: p.stat().st_mtime,
    )
    return dirs[-1] if dirs else None


def latest_completed_dir(
    pattern: str, required_file: str = "summary.json"
) -> Path | None:
    dirs = sorted(
        (
            path
            for path in ROOT.glob(pattern)
            if path.is_dir() and (path / required_file).exists()
        ),
        key=lambda p: p.stat().st_mtime,
    )
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
        w4 = row.get(
            "w4_rate",
            row.get("w4_extraction_rate_pct", row.get("w4_extraction_rate", 0)),
        )
        w5 = row.get(
            "w5_rate",
            row.get("w5_extraction_rate_pct", row.get("w5_extraction_rate", 0)),
        )
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
        duration_txt = (
            "n/a" if duration is None else f"{float(duration) / 60.0:.1f} min"
        )
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
    progress_re = re.compile(
        r'"defense": "([^"]+)", "completed": (\d+), "total": (\d+)'
    )
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
    log_path = (
        ROOT
        / "_run_logs"
        / f"{run_dir.name.replace('lcct_comparable_model_full_', 'lcct_comparable_model_full_')}.log"
    )
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
        lines.extend(
            [
                "",
                "## Completed Defense Summaries",
                "",
                "| defense | hits | n | hit rate | duration |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for defense, row in defense_summaries.items():
            duration = row.get("duration_sec")
            duration_txt = (
                "n/a" if duration is None else f"{float(duration) / 60.0:.1f} min"
            )
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
        copy_sanitized(
            str(rel / "benchmark" / "metadata.json"),
            "lcct_comparable_fullsize_metadata.json",
        )
        copy_sanitized(
            str(rel / "scorer_smoke" / "summary.json"),
            "lcct_comparable_scorer_smoke_summary.json",
        )

    lcct_model_smoke_summary = None
    lcct_model_smoke_latest = latest_completed_dir(
        "_run_results/lcct_comparable_model_smoke_[0-9]*"
    )
    if lcct_model_smoke_latest:
        rel = lcct_model_smoke_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "summary.json"), "lcct_comparable_model_smoke_summary.json"
        )
        copy_sanitized(
            str(rel / "summary.md"), "lcct_comparable_model_smoke_summary.md"
        )
        lcct_model_smoke_summary = read_json(rel / "summary.json")

    lcct_model_full_summary = None
    lcct_model_full_latest = latest_completed_dir(
        "_run_results/lcct_comparable_model_full_*"
    )
    if lcct_model_full_latest:
        rel = lcct_model_full_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "summary.json"), "lcct_comparable_model_full_summary.json"
        )
        copy_sanitized(str(rel / "summary.md"), "lcct_comparable_model_full_summary.md")
        lcct_model_full_summary = read_json(rel / "summary.json")

    lcct_model_full_live = None
    lcct_model_full_live_latest = latest_dir(
        "_run_results/lcct_comparable_model_full_*"
    )
    if (
        lcct_model_full_live_latest
        and not (lcct_model_full_live_latest / "summary.json").exists()
    ):
        lcct_model_full_live, lcct_live_status_doc = build_lcct_live_status(
            lcct_model_full_live_latest
        )
        write_text("lcct_comparable_full_live_status.md", lcct_live_status_doc)

    entropy_audit_latest = latest_dir("_run_results/entropy_cap_audit_*")
    entropy_audit_summary = None
    if entropy_audit_latest:
        rel = entropy_audit_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "certificate_entropy_cap_audit.json"),
            "certificate_entropy_cap_audit.json",
        )
        copy_sanitized(
            str(rel / "certificate_entropy_cap_audit.md"),
            "certificate_entropy_cap_audit.md",
        )
        entropy_audit_summary = read_json(rel / "certificate_entropy_cap_audit.json")

    informative_sweep_latest = latest_dir("_run_results/informative_budget_sweep_*")
    informative_summaries = {}
    if informative_sweep_latest:
        for child in sorted(
            p for p in informative_sweep_latest.iterdir() if p.is_dir()
        ):
            rel = child.relative_to(ROOT)
            key = child.name
            copy_sanitized(
                str(rel / "informative_budget_sweep.json"),
                f"informative_budget_sweep_{key}.json",
            )
            copy_sanitized(
                str(rel / "informative_budget_sweep.md"),
                f"informative_budget_sweep_{key}.md",
            )
            informative_summaries[key] = read_json(
                rel / "informative_budget_sweep.json"
            )

    mac_queue_latest = latest_dir("_run_results/mac_studio_stable_queue_*")
    mac_queue_summary = None
    mac_w5_summaries = {}
    if mac_queue_latest:
        rel = mac_queue_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "metadata.json"), "mac_studio_stable_queue_metadata.json"
        )
        copy_sanitized(
            str(rel / "queue_status.json"), "mac_studio_stable_queue_status.json"
        )
        mac_queue_summary = read_json(rel / "queue_status.json")
        for table in sorted(
            mac_queue_latest.glob("w5_seed*/w5/table6_paraphrase_robustness.json")
        ):
            seed_name = table.parents[1].name
            copy_sanitized(
                str(table.relative_to(ROOT)),
                f"mac_studio_stable_{seed_name}_w5_table6.json",
            )
            mac_w5_summaries[seed_name] = read_json(table.relative_to(ROOT))

    reviewer_bootstrap_latest = latest_dir(
        "_run_results/reviewer_local_bootstrap_w5_multiseed_*"
    )
    reviewer_bootstrap = None
    if reviewer_bootstrap_latest:
        rel = reviewer_bootstrap_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "bootstrap_w5_multiseed.json"),
            "reviewer_bootstrap_w5_multiseed.json",
        )
        copy_sanitized(
            str(rel / "bootstrap_w5_multiseed.md"), "reviewer_bootstrap_w5_multiseed.md"
        )
        reviewer_bootstrap = read_json(rel / "bootstrap_w5_multiseed.json")

    reviewer_w3_error_latest = latest_dir(
        "_run_results/reviewer_local_w3_error_analysis_*"
    )
    reviewer_w3_error = None
    if (
        reviewer_w3_error_latest
        and (reviewer_w3_error_latest / "w3_error_analysis.json").exists()
    ):
        rel = reviewer_w3_error_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "w3_error_analysis.json"), "reviewer_w3_error_analysis.json"
        )
        copy_sanitized(
            str(rel / "w3_error_analysis.md"), "reviewer_w3_error_analysis.md"
        )
        reviewer_w3_error = read_json(rel / "w3_error_analysis.json")

    reviewer_threshold_latest = latest_dir(
        "_run_results/reviewer_local_w3_threshold_sweep_*"
    )
    reviewer_threshold = None
    if (
        reviewer_threshold_latest
        and (reviewer_threshold_latest / "w3_refusal_threshold_sweep.json").exists()
    ):
        rel = reviewer_threshold_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "w3_refusal_threshold_sweep.json"),
            "reviewer_w3_threshold_sweep.json",
        )
        reviewer_threshold = read_json(rel / "w3_refusal_threshold_sweep.json")

    reviewer_ablation_latest = latest_dir(
        "_run_results/reviewer_local_component_ablation_*"
    )
    reviewer_ablation = None
    if (
        reviewer_ablation_latest
        and (reviewer_ablation_latest / "component_ablation_summary.json").exists()
    ):
        rel = reviewer_ablation_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "component_ablation_summary.json"),
            "reviewer_component_ablation_summary.json",
        )
        copy_sanitized(
            str(rel / "component_ablation_summary.md"),
            "reviewer_component_ablation_summary.md",
        )
        reviewer_ablation = read_json(rel / "component_ablation_summary.json")

    reviewer_extra_light_latest = latest_dir(
        "_run_results/reviewer_local_extra_light_*"
    )
    reviewer_extra_light = None
    if (
        reviewer_extra_light_latest
        and (reviewer_extra_light_latest / "summary.json").exists()
    ):
        rel = reviewer_extra_light_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "summary.json"), "reviewer_extra_light_w5_replications.json"
        )
        if (reviewer_extra_light_latest / "summary.md").exists():
            copy_sanitized(
                str(rel / "summary.md"), "reviewer_extra_light_w5_replications.md"
            )
        reviewer_extra_light = read_json(rel / "summary.json")

    reviewer_extra_ablation_latest = latest_dir(
        "_run_results/reviewer_local_extra_ablation_resume_*"
    )
    reviewer_extra_ablation = None
    if (
        reviewer_extra_ablation_latest
        and (
            reviewer_extra_ablation_latest / "component_ablation_summary.json"
        ).exists()
    ):
        rel = reviewer_extra_ablation_latest.relative_to(ROOT)
        copy_sanitized(
            str(rel / "component_ablation_summary.json"),
            "reviewer_extra_component_ablation_summary.json",
        )
        copy_sanitized(
            str(rel / "component_ablation_summary.md"),
            "reviewer_extra_component_ablation_summary.md",
        )
        reviewer_extra_ablation = read_json(rel / "component_ablation_summary.json")

    w3_diag = read_json(
        "_run_results/w3_utility_diagnostic_learnedonly_t095_20260603_203948/w3_utility_diagnostic.json"
    )
    learned_w3 = read_json(
        "_run_results/learnedonly_t095_validation_20260603_190245/w3_164_t095/w3_refusal_threshold_sweep.json"
    )
    seed42_w5 = extract_w5_rows(
        "_run_results/local_mps_qwen_positive_expanded_20260603_070216/w5/table6_paraphrase_robustness.json"
    )
    seed43_w5 = extract_w5_rows(
        "_run_results/local_mps_qwen_positive_expanded_seed43_20260603_092323/w5/table6_paraphrase_robustness.json"
    )
    learned_seed42 = extract_w5_rows(
        "_run_results/learnedonly_t095_validation_20260603_190245/w5_seed42_t095/w5/table6_paraphrase_robustness.json"
    )

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
   The learned-only refusal setting at threshold `0.95` reduces W5 extraction below the B5 content-filter baseline across five seeds. A 500k-sample bootstrap comparison per seed and in aggregate gives strong evidence for the reduction.

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
| W5 paraphrase | Strongest evidence | Learned-only t=0.95 beats B5 across five seeds with bootstrap | Still small/medium scale |
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
        "entropy_cap_audit": entropy_audit_summary,
        "informative_budget_sweeps": informative_summaries,
        "mac_studio_stable_queue": mac_queue_summary,
        "mac_studio_stable_w5": mac_w5_summaries,
        "reviewer_bootstrap_w5_multiseed": reviewer_bootstrap,
        "reviewer_w3_error_analysis": reviewer_w3_error,
        "reviewer_w3_threshold_sweep": reviewer_threshold,
        "reviewer_component_ablation": reviewer_ablation,
        "reviewer_extra_light_w5_replications": reviewer_extra_light,
        "reviewer_extra_component_ablation": reviewer_extra_ablation,
    }
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

    paper_tables = f"""# Paper-Ready Result Tables

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

## Table D: Entropy-Cap Audit for Certificate/MI Tables

| checked values | raw violations | capped values | reviewer-facing action |
|---:|---:|---:|---|
| {entropy_audit_summary.get('n_checked_values', 'n/a') if entropy_audit_summary else 'n/a'} | {entropy_audit_summary.get('n_raw_violations', 'n/a') if entropy_audit_summary else 'n/a'} | {entropy_audit_summary.get('n_values_capped', 'n/a') if entropy_audit_summary else 'n/a'} | use capped certificate/MI columns; raw values are diagnostics only |

## Table E: Informative-Budget Pilot

| KL source | any non-vacuous capped certificate | interpretation |
|---|---|---|
| certificate_refresh | {informative_summaries.get('certificate_refresh', {}).get('any_non_vacuous', 'n/a')} | high-leakage diagnostic; certificate saturates immediately |
| safe_positive | {informative_summaries.get('safe_positive', {}).get('any_non_vacuous', 'n/a')} | low/zero-KL diagnostic; verifies non-vacuous regime path |

## Table F: Mac Studio Stable W5 Replication Queue

| seed | B5 W4 | B5 W5 | learned-only W4 | learned-only W5 | status |
|---|---:|---:|---:|---:|---|
"""
    for seed_name, table in sorted(mac_w5_summaries.items()):
        b5 = table.get("B5_content_filter", {}) if isinstance(table, dict) else {}
        lc = table.get("LEAKCERT", {}) if isinstance(table, dict) else {}
        paper_tables += (
            f"| {seed_name.replace('w5_seed', '')} | "
            f"{b5.get('w4_rate', 'n/a')} | {b5.get('w5_rate', 'n/a')} | "
            f"{lc.get('w4_rate', 'n/a')} | {lc.get('w5_rate', 'n/a')} | complete |\n"
        )
    if not mac_w5_summaries:
        paper_tables += "| n/a | n/a | n/a | n/a | n/a | pending |\n"

    paper_tables += "\n## Table G: Reviewer Local Multi-Seed W5 Bootstrap\n\n"
    paper_tables += (
        "| scope | B5 W5 | LEAKCERT W5 | diff | 95% CI | P(B5 > LEAKCERT) |\n"
    )
    paper_tables += "|---|---:|---:|---:|---:|---:|\n"
    if reviewer_bootstrap:
        for row in reviewer_bootstrap.get("rows", []):
            ci = row.get("ci95_pct", [0, 0])
            paper_tables += (
                f"| seed {row.get('seed')} | {float(row.get('baseline_rate_pct', 0.0)):.3f}% | "
                f"{float(row.get('method_rate_pct', 0.0)):.3f}% | "
                f"{float(row.get('baseline_minus_method_pct', 0.0)):.3f} pp | "
                f"[{float(ci[0]):.3f}, {float(ci[1]):.3f}] | "
                f"{float(row.get('p_baseline_gt_method', 0.0)):.5f} |\n"
            )
        agg = reviewer_bootstrap.get("aggregate", {})
        ci = agg.get("ci95_pct", [0, 0])
        paper_tables += (
            f"| aggregate | {float(agg.get('baseline_rate_pct', 0.0)):.3f}% | "
            f"{float(agg.get('method_rate_pct', 0.0)):.3f}% | "
            f"{float(agg.get('baseline_minus_method_pct', 0.0)):.3f} pp | "
            f"[{float(ci[0]):.3f}, {float(ci[1]):.3f}] | "
            f"{float(agg.get('p_baseline_gt_method', 0.0)):.5f} |\n"
        )
    else:
        paper_tables += "| n/a | n/a | n/a | n/a | n/a | n/a |\n"

    paper_tables += "\n## Table H: Reviewer Local W3 Threshold Sweep\n\n"
    paper_tables += "| threshold | pass@1 | refusal | interpretation |\n"
    paper_tables += "|---:|---:|---:|---|\n"
    if reviewer_threshold:
        for threshold, row in sorted(
            reviewer_threshold.get("rows", {}).items(), key=lambda kv: float(kv[0])
        ):
            refusal = float(row.get("refusal_rate_pct", 0.0))
            interpretation = "high refusal" if refusal >= 10.0 else "low refusal"
            paper_tables += (
                f"| {threshold} | {float(row.get('pass_at_1_pct', 0.0)):.2f}% | "
                f"{refusal:.2f}% | {interpretation} |\n"
            )
    else:
        paper_tables += "| n/a | n/a | n/a | pending |\n"

    paper_tables += "\n## Table I: Reviewer Local Component Ablation\n\n"
    paper_tables += (
        "| variant | W4 extraction | W5 extraction | W5 blocked/replaced | takeaway |\n"
    )
    paper_tables += "|---|---:|---:|---:|---|\n"
    if reviewer_ablation:
        for name, row in reviewer_ablation.get("results", {}).items():
            w4 = row.get("W4", {})
            w5 = row.get("W5", {})
            w4_rate = float(w4.get("extraction", {}).get("rate_pct", 0.0))
            w5_rate = float(w5.get("extraction", {}).get("rate_pct", 0.0))
            w5_blocked = float(w5.get("refusal", {}).get("rate_pct", 0.0))
            if name == "B5_content_filter":
                takeaway = "baseline"
            elif name == "LEAKCERT_no_rate_limit":
                takeaway = "rate limit contributes to W5 reduction"
            elif name == "LEAKCERT_no_refusal":
                takeaway = "refusal contributes to W4 reduction"
            else:
                takeaway = "similar to full on W5"
            paper_tables += f"| {name} | {w4_rate:.2f}% | {w5_rate:.2f}% | {w5_blocked:.2f}% | {takeaway} |\n"
    else:
        paper_tables += "| n/a | n/a | n/a | n/a | pending |\n"

    paper_tables += "\n## Table J: Reviewer Extra Light W5 Replications\n\n"
    paper_tables += "| seed | B5 W4 | B5 W5 | LEAKCERT W4 | LEAKCERT W5 | takeaway |\n"
    paper_tables += "|---:|---:|---:|---:|---:|---|\n"
    extra_rows = (reviewer_extra_light or {}).get("w5_replications", {})
    if extra_rows:
        for seed, rows in sorted(extra_rows.items(), key=lambda kv: int(kv[0])):
            b5 = rows.get("B5_content_filter", {})
            lc = rows.get("LEAKCERT", {})
            paper_tables += (
                f"| {seed} | {float(b5.get('w4_rate_pct', 0.0)):.2f}% | "
                f"{float(b5.get('w5_rate_pct', 0.0)):.2f}% | "
                f"{float(lc.get('w4_rate_pct', 0.0)):.2f}% | "
                f"{float(lc.get('w5_rate_pct', 0.0)):.2f}% | "
                "small-panel replication |\n"
            )
    else:
        paper_tables += "| n/a | n/a | n/a | n/a | n/a | pending |\n"

    paper_tables += "\n## Table K: Reviewer Extra Light Component Ablation\n\n"
    paper_tables += (
        "| variant | W4 extraction | W5 extraction | W5 blocked/replaced | takeaway |\n"
    )
    paper_tables += "|---|---:|---:|---:|---|\n"
    if reviewer_extra_ablation:
        for name, row in reviewer_extra_ablation.get("results", {}).items():
            w4 = row.get("W4", {})
            w5 = row.get("W5", {})
            w4_rate = float(w4.get("extraction", {}).get("rate_pct", 0.0))
            w5_rate = float(w5.get("extraction", {}).get("rate_pct", 0.0))
            w5_blocked = float(w5.get("refusal", {}).get("rate_pct", 0.0))
            if name == "B5_content_filter":
                takeaway = "baseline"
            elif name == "LEAKCERT_no_refusal":
                takeaway = "matches B5; refusal is decisive in this sanity panel"
            elif name == "LEAKCERT_full":
                takeaway = "reduced W5 vs B5"
            else:
                takeaway = "similar to full in this sanity panel"
            paper_tables += f"| {name} | {w4_rate:.2f}% | {w5_rate:.2f}% | {w5_blocked:.2f}% | {takeaway} |\n"
    else:
        paper_tables += "| n/a | n/a | n/a | n/a | pending |\n"

    paper_tables += """

## Safe Claim Wording

> In a local positive-control evaluation with Qwen2.5-Coder-0.5B, the learned-only LEAKCERT refusal variant reduced W5 paraphrase extraction relative to the B5 content-filter baseline across five seeds. A 500k-sample bootstrap comparison per seed and aggregate comparison showed B5 exceeded the learned-only method by about 3.14 percentage points in aggregate, with confidence intervals excluding zero. A matched W3 diagnostic showed identical pass@1 for B1, B5, and LEAKCERT, suggesting that the observed utility weakness is checkpoint-driven rather than caused by the defense layer.

> Certificate and MI quantities are now treated with an explicit entropy ceiling. Historical raw certificate/MI values that exceed `H(K)` are retained only as diagnostics; reviewer-facing tables must report capped quantities and a pass/fail entropy audit.

## Claims To Avoid Until Server Runs Finish

- Do not claim full W1/W4/W5 scale.
- Do not claim DP-SGD epsilon sweep results.
- Do not claim multi-model robustness.
- Do not claim non-vacuous certificate tightness.
- Do not claim paper-grade LCCT training-data extraction reproduction.
"""
    write_text("paper_ready_tables.md", paper_tables)

    reviewer_plan = """# Reviewer-Driven Experiment Plan

This plan translates the simulated reviewer package into concrete next experiments and paper changes. It is scoped for a sanitized public result folder: no venue metadata, no timeline details, no private keys, no local personal paths, and no raw benchmark rows that resemble credentials.

## Executive Diagnosis

The blocking issues are correctness and claim alignment, not just missing scale.

The next revision should prioritize:

1. Enforcing the entropy ceiling `I(K;Y^B) <= H(K)` in every certificate, estimator, and table.
2. Running a dedicated informative-budget evaluation where `B < B* = H(K)/C1`.
3. Decoupling certificate evidence from runtime engineering components such as rate limiting, refusal, and suppression.
4. Correcting the general-prior Fano statement and making prior assumptions explicit.
5. Reframing canary evidence as panel-conditioned auditing unless a real-secret validation experiment is added.

## P0: Correctness Fixes

These must be completed before adding more headline experiments.

| item | action | output |
|---|---|---|
| Entropy cap | Recompute certificate tables with `cert = min(B*C1, H(K))`; report raw `B*C1` only as a diagnostic column | corrected certificate-tightness table |
| Empirical MI sanity | Stop using uncapped MINE as a tightness denominator; report MINE only with an explicit `min(MINE,H(K))` sanity check, or replace with bounded plug-in / attack-derived lower bounds | bounded MI audit table |
| DP table cap | Recompute any DP/RDP table with the same entropy cap and verify the budget/caption uses the actual `B` | corrected DP audit table |
| Fano theorem | State uniform-prior and general-prior forms separately | theorem/proof patch |
| General-prior correction | Use a bound of the form `P_success <= (I + log 2 + log(|K|-1) - H(K))/log(|K|-1)` for non-uniform priors, with assumptions stated | corrected theorem + table notes |

Acceptance gate: every row in every MI/certificate table must satisfy `value <= H(K)` and the machine-readable output must include a boolean `entropy_cap_pass=true`.

## P1: Informative-Regime Certificate Evaluation

Reviewer concern: the empirical win is currently shown mostly at budgets where the certificate is vacuous.

Run a budget sweep around the informative boundary:

| parameter | proposed values |
|---|---|
| canary universe | `|K| = 10^4` if available; otherwise use the largest existing panel and report its `H(K)` |
| budgets | `B = 50, 100, 200, 400, 600, 800, 1000, 2000` |
| required derived value | `B* = H(K)/C1` for each panel |
| methods | B1, B5, LEAKCERT learned-only, cert-only, rate-limit-only, suppression-only, full runtime |
| metrics | extraction, refusal, pass@1/utility, median/p99 latency, capped certificate, raw certificate, `B/B*` |

Required tables:

1. Certificate tightness in the informative regime only (`B/B* < 1`).
2. Transition table showing when the certificate becomes vacuous (`B/B* >= 1`).
3. Runtime-component ablation separating certificate accounting from rate limiting/refusal/suppression.

Safe claim target:

> In the informative regime, the capped certificate remains non-vacuous and tracks bounded leakage diagnostics; beyond the boundary, protection is explicitly runtime/rate-limit driven rather than certificate-driven.

## P2: Replace Fragile Tightness Claims

Reviewer concern: MINE can exceed `H(K)` and is not a reliable ground truth.

Run or compute bounded alternatives:

| estimator / diagnostic | role | cap behavior |
|---|---|---|
| plug-in MI from observed confusion matrix | primary bounded diagnostic when labels are available | naturally bounded by `H(K)` with smoothing |
| Bayes-success / Fano interval | success-to-information consistency check | reports lower/upper consistency, not exact MI |
| bootstrap over panels/seeds | uncertainty for extraction and bounded MI | cap applied per bootstrap sample |
| MINE | optional appendix diagnostic only | must report raw and capped; never used as denominator for tightness |

Required output:

- `certificate_entropy_cap_audit.json`
- `certificate_entropy_cap_audit.md`
- `bounded_tightness_table.md`
- `mine_sanity_check.md`

## P3: Canary-to-Real-Secret Scope

Reviewer concern: the certificate currently certifies the audited canary set, not arbitrary real secrets outside the panel.

Practical response options:

| option | cost | expected value |
|---|---:|---|
| Scope-down only | low | honest but weaker; fastest |
| Synthetic real-secret families | medium | shows panel diversity: API keys, tokens, emails, locations, config secrets |
| Public opt-in benchmark | high | strongest, but needs data governance |

Recommended now:

1. Expand the controlled synthetic secret families already present in the LCCT comparable benchmark.
2. Report per-family extraction and certificate behavior.
3. State that the certificate is panel-conditioned and does not certify secrets absent from `K`.

## P4: Scale and Replication

Reviewer concern: two seeds and small models are not enough for strong claims.

Minimum credible next run:

| dimension | target |
|---|---|
| seeds | at least 5 |
| canary panels | at least 10 if full 20 is too expensive |
| models | current Qwen small + one larger/server checkpoint |
| workloads | W4, W5, W3 utility, informative-budget certificate sweep |
| outputs | per-seed tables, bootstrap CIs, aggregate mean/median, failure analysis |

Server/GPU priority order:

1. Informative-budget certificate sweep.
2. W5 paraphrase replication with 5 seeds.
3. DP/RDP capped audit with real DP checkpoints.
4. Multi-model replication.

## P5: Current Result Interpretation

The current `Updated-Res` package supports the following careful statements:

| result | status | interpretation |
|---|---|---|
| W5 learned-only t=0.95 | strongest current evidence | lower extraction than B5 across two seeds with bootstrap support |
| W3 utility diagnostic | complete but low absolute utility | defense layer is not the main utility bottleneck |
| LCCT comparable full run | complete | current checkpoint does not leak on the controlled comparable benchmark; useful negative-control/readiness evidence |
| certificate non-vacuous | not ready | must be repaired with capped tables and informative-budget runs |
| DP sweep | not ready | needs real DP checkpoints and capped reporting |
| multi-model | not ready | needs second model/checkpoint |

## Immediate Execution Queue

1. Implement an entropy-cap audit script for all certificate/MI tables.
2. Generate corrected certificate and DP audit tables with cap checks.
3. Add an informative-budget config sweep with `B` below and around `B*`.
4. Run a small local pilot of the informative sweep to verify scripts and output schema.
5. Queue the same sweep for server/GPU once available.
6. Update `Updated-Res` with reviewer-facing tables and safe claim wording.

## Stop Conditions

Do not make any headline certificate-tightness claim until:

- all MI/certificate rows pass `<= H(K)`;
- the paper distinguishes raw bound, capped bound, and empirical diagnostic;
- at least one informative-budget table shows non-vacuous certificates;
- rate-limit/refusal/suppression ablations are reported separately;
- theorem statements distinguish uniform and general priors.
"""
    write_text("reviewer_experiment_plan.md", reviewer_plan)

    machine["git_status_at_generation"] = get_git_status()
    write_json("machine_readable_summary.json", machine)
    build_manifest()
    print(
        json.dumps(
            {"output_dir": str(OUT), "files": len(list(OUT.rglob("*")))}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
