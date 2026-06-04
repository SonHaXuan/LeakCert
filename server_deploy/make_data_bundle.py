#!/usr/bin/env python3
"""Build a private server data/checkpoint payload from a local manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "experiments" / "configs" / "sp2027_real_inputs_template.yaml"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_rows(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file())


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data.get("items"), list):
        raise SystemExit("manifest must contain an items list")
    return data


def set_dotted(cfg: dict[str, Any], dotted: str, value: Any) -> None:
    if value in ("", None):
        return
    cur = cfg
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def render_config(manifest: dict[str, Any], payload_root: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(TEMPLATE.read_text())
    by_id = {item["id"]: item for item in manifest["items"]}

    def server_abs(item_id: str) -> str:
        item = by_id.get(item_id)
        if not item:
            return ""
        server_path = item.get("server_path") or ""
        return f"${{LEAKCERT_RUN_ROOT}}/{server_path}".rstrip("/")

    overrides = dict(manifest.get("config_overrides") or {})
    defaults = {
        "corpus.path": server_abs("training_corpus"),
        "corpus.lcct_path": server_abs("lcct_jsonl"),
        "finetune.output_dir": server_abs("target_checkpoint"),
        "finetune_mid.output_dir": server_abs("mid_checkpoint"),
        "finetune_dp.checkpoints.1": server_abs("dp_eps_1"),
        "finetune_dp.checkpoints.2": server_abs("dp_eps_2"),
        "finetune_dp.checkpoints.4": server_abs("dp_eps_4"),
        "finetune_dp.checkpoints.8": server_abs("dp_eps_8"),
        "finetune_dp.checkpoints.16": server_abs("dp_eps_16"),
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        set_dotted(cfg, key, value)
    return cfg


def copy_item(item: dict[str, Any], stage_root: Path) -> dict[str, Any] | None:
    item_id = item.get("id")
    source = item.get("source") or ""
    optional = bool(item.get("optional"))
    if not source or source.startswith("TODO_"):
        if optional:
            return None
        raise SystemExit(f"missing source for required item {item_id}: {source!r}")

    src = Path(source).expanduser()
    if not src.is_absolute():
        src = (ROOT / src).resolve()
    if not src.exists():
        if optional:
            return None
        raise SystemExit(f"source for {item_id} does not exist: {src}")

    server_path = item.get("server_path")
    if not server_path or Path(server_path).is_absolute() or ".." in Path(server_path).parts:
        raise SystemExit(f"invalid relative server_path for {item_id}: {server_path!r}")
    dst = stage_root / server_path
    dst.parent.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".DS_Store"))
    else:
        shutil.copy2(src, dst)

    files = []
    total = 0
    for path in file_rows(dst):
        size = path.stat().st_size
        total += size
        files.append(
            {
                "path": str(path.relative_to(stage_root)),
                "size_bytes": size,
                "sha256": sha256(path),
            }
        )
    return {
        "id": item_id,
        "kind": item.get("kind"),
        "server_path": server_path,
        "source_basename": src.name,
        "required_for": item.get("required_for", []),
        "n_files": len(files),
        "size_bytes": total,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / f"leakcert_server_payload_{ts}"
    payload_root = stage / "payload"
    payload_root.mkdir(parents=True)

    copied = []
    for item in manifest["items"]:
        row = copy_item(item, payload_root)
        if row:
            copied.append(row)

    cfg = render_config(manifest, payload_root)
    config_dir = payload_root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "server_real_inputs.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))

    installed_manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_manifest": str(Path(args.manifest).resolve()),
        "repo_commit": os.popen("git rev-parse HEAD 2>/dev/null").read().strip() or "unknown",
        "items": copied,
        "config": "configs/server_real_inputs.yaml",
        "notes": [
            "This payload is private and should not be committed.",
            "Install under LEAKCERT_RUN_ROOT on the server.",
        ],
    }
    (payload_root / "data_bundle_manifest.json").write_text(json.dumps(installed_manifest, indent=2) + "\n")

    bundle = out_dir / f"leakcert_server_payload_{ts}.tgz"
    with tarfile.open(bundle, "w:gz") as tar:
        tar.add(payload_root, arcname="payload")

    shutil.rmtree(stage)
    print(json.dumps({
        "bundle": str(bundle),
        "items": len(copied),
        "size_bytes": bundle.stat().st_size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
