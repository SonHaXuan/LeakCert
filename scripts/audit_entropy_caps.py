#!/usr/bin/env python3
"""Audit and correct entropy caps for certificate/MI/DP result tables.

The reviewer-critical invariant is I(K;Y^B) <= H(K).  This script never edits
raw run outputs in place.  It writes capped, reviewer-facing JSON/Markdown
tables into a fresh output directory.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


VALUE_KEYS = {
    "cert_nats",
    "hoeffding_cert_nats",
    "bernstein_cert_nats",
    "empirical_mi_nats",
    "emp_mi_nats",
    "leakcert_nats",
    "leakcert_cert",
    "dp_bound_nats",
    "dp_bound",
    "certificate_nats",
    "hoeffding_cert",
    "bernstein_cert",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def sibling_entropy(path: Path) -> tuple[float | None, str]:
    """Find H(K) near a certificate table."""
    candidates = [
        path.parent / "table4_prior.json",
        path.parent / "table4_prior_sweep.json",
        path.parent / "table4.json",
        path.parent / "certificate" / "table4_prior.json",
        path.parent.parent / "certificate" / "table4_prior.json",
    ]
    for cand in candidates:
        if cand.exists():
            try:
                data = read_json(cand)
            except Exception:
                continue
            rows = data if isinstance(data, list) else data.get("rows", [])
            if isinstance(rows, list):
                for row in rows:
                    if (
                        isinstance(row, dict)
                        and row.get("prior") == "uniform"
                        and row.get("H_K") is not None
                    ):
                        return float(row["H_K"]), str(cand.relative_to(ROOT))
                for row in rows:
                    if isinstance(row, dict) and row.get("H_K") is not None:
                        return float(row["H_K"]), str(cand.relative_to(ROOT))
    return None, "missing"


def cap_value(value: Any, entropy: float | None) -> dict[str, Any]:
    try:
        raw = float(value)
    except Exception:
        return {
            "raw": value,
            "capped": value,
            "entropy_cap_pass": None,
            "cap_applied": False,
        }
    if entropy is None:
        return {
            "raw": raw,
            "capped": raw,
            "entropy_cap_pass": None,
            "cap_applied": False,
        }
    capped = min(raw, entropy)
    return {
        "raw": raw,
        "capped": capped,
        "entropy_cap_pass": raw <= entropy + 1e-9,
        "cap_applied": raw > entropy + 1e-9,
    }


def audit_row(row: dict[str, Any], entropy: float | None) -> dict[str, Any]:
    out = dict(row)
    capped_fields = {}
    for key in sorted(VALUE_KEYS):
        if key in row and row[key] is not None:
            capped_fields[key] = cap_value(row[key], entropy)
            if isinstance(capped_fields[key]["capped"], (int, float)):
                out[f"{key}_capped"] = capped_fields[key]["capped"]
    out["entropy_H_K_nats"] = entropy
    out["entropy_cap_audit"] = capped_fields
    passes = [
        v["entropy_cap_pass"]
        for v in capped_fields.values()
        if v["entropy_cap_pass"] is not None
    ]
    out["entropy_cap_pass"] = all(passes) if passes else None
    out["any_cap_applied"] = any(v["cap_applied"] for v in capped_fields.values())
    return out


def audit_file(path: Path, default_entropy: float | None) -> dict[str, Any]:
    data = read_json(path)
    entropy, entropy_source = sibling_entropy(path)
    if entropy is None and default_entropy is not None:
        entropy = default_entropy
        entropy_source = "default_entropy_nats"
    rows = data if isinstance(data, list) else data.get("rows", [])
    audited_rows = []
    if isinstance(rows, list):
        for row in rows:
            audited_rows.append(
                audit_row(row, entropy) if isinstance(row, dict) else row
            )
    violations = 0
    capped = 0
    checked = 0
    for row in audited_rows:
        if not isinstance(row, dict):
            continue
        for field in row.get("entropy_cap_audit", {}).values():
            if field.get("entropy_cap_pass") is not None:
                checked += 1
                if not field["entropy_cap_pass"]:
                    violations += 1
                if field.get("cap_applied"):
                    capped += 1
    return {
        "source": str(path.relative_to(ROOT)),
        "entropy_H_K_nats": entropy,
        "entropy_source": entropy_source,
        "n_rows": len(audited_rows),
        "n_checked_values": checked,
        "n_raw_violations": violations,
        "n_values_capped": capped,
        "entropy_cap_pass": violations == 0 if checked else None,
        "rows": audited_rows,
    }


def discover(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for item in paths:
        p = ROOT / item
        if any(ch in item for ch in "*?[]"):
            out.extend(sorted(ROOT.glob(item)))
        elif p.exists():
            out.append(p)
    seen = set()
    dedup = []
    for p in out:
        if p.is_file() and p.suffix == ".json" and p not in seen:
            seen.add(p)
            dedup.append(p)
    return dedup


def markdown_report(audits: list[dict[str, Any]]) -> str:
    lines = [
        "# Entropy-Cap Audit",
        "",
        "Invariant: every mutual-information, certificate, or DP-bound quantity must satisfy `value <= H(K)`.",
        "",
        "Raw historical values are preserved as diagnostics. Reviewer-facing values should use the capped columns.",
        "",
        "## File Summary",
        "",
        "| source | H(K) | H source | checked | raw violations | capped values | pass |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for audit in audits:
        h = audit["entropy_H_K_nats"]
        h_text = "missing" if h is None else f"{h:.3f}"
        lines.append(
            f"| `{audit['source']}` | {h_text} | `{audit['entropy_source']}` | "
            f"{audit['n_checked_values']} | {audit['n_raw_violations']} | "
            f"{audit['n_values_capped']} | {audit['entropy_cap_pass']} |"
        )
    lines.extend(["", "## Reviewer-Facing Interpretation", ""])
    total_violations = sum(a["n_raw_violations"] for a in audits)
    if total_violations:
        lines.append(
            f"The audit found `{total_violations}` raw values above the entropy ceiling. "
            "These rows must not be used as certificate-tightness claims without the capped columns."
        )
    else:
        lines.append("All checked raw values satisfy the entropy ceiling.")
    lines.extend(
        [
            "",
            "Recommended paper action:",
            "",
            "- Report `raw_*` only as diagnostic/unbounded composition quantities.",
            "- Use `*_capped` for MI/certificate claims.",
            "- Do not compute tightness ratios against uncapped MINE.",
            "- Include `entropy_cap_pass` in table-generation CI.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--default-entropy-nats", type=float)
    parser.add_argument(
        "paths",
        nargs="*",
        default=[
            "_run_results/*/certificate/table1_certificate.json",
            "_run_results/*/certificate/table3_tightness.json",
            "_run_results/*/certificate/table4_prior.json",
            "_run_results/*/certificate/table8_dp_comparison.json",
            "_run_results/*/table1_certificate_sweep.json",
        ],
    )
    args = parser.parse_args()

    out = ROOT / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    files = discover(args.paths)
    audits = [audit_file(path, args.default_entropy_nats) for path in files]

    for audit in audits:
        safe_name = audit["source"].replace("/", "__")
        write_json(out / "audited_tables" / safe_name, audit)
    aggregate = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "n_files": len(audits),
        "n_checked_values": sum(a["n_checked_values"] for a in audits),
        "n_raw_violations": sum(a["n_raw_violations"] for a in audits),
        "n_values_capped": sum(a["n_values_capped"] for a in audits),
        "entropy_cap_pass": all(
            a["entropy_cap_pass"] for a in audits if a["entropy_cap_pass"] is not None
        ),
        "files": [
            {
                "source": a["source"],
                "entropy_H_K_nats": a["entropy_H_K_nats"],
                "entropy_source": a["entropy_source"],
                "n_checked_values": a["n_checked_values"],
                "n_raw_violations": a["n_raw_violations"],
                "n_values_capped": a["n_values_capped"],
                "entropy_cap_pass": a["entropy_cap_pass"],
            }
            for a in audits
        ],
    }
    write_json(out / "certificate_entropy_cap_audit.json", aggregate)
    (out / "certificate_entropy_cap_audit.md").write_text(markdown_report(audits))
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
