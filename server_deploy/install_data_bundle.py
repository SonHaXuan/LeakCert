#!/usr/bin/env python3
"""Install and verify a LeakCert private payload on a server."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    dest = destination.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise SystemExit(f"unsafe tar path: {member.name}")
    try:
        tar.extractall(dest, filter="data")
    except TypeError:
        tar.extractall(dest)


def copy_payload(payload: Path, run_root: Path) -> None:
    for child in payload.iterdir():
        if child.name == "data_bundle_manifest.json":
            continue
        dst = run_root / child.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if child.is_dir():
            for src in child.rglob("*"):
                rel = src.relative_to(child)
                target = dst / rel
                if src.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
        else:
            shutil.copy2(child, dst)


def verify(manifest: dict, run_root: Path) -> list[dict]:
    failures = []
    for item in manifest.get("items", []):
        for row in item.get("files", []):
            path = run_root / row["path"]
            if not path.exists():
                failures.append({"path": row["path"], "error": "missing"})
                continue
            got = sha256(path)
            if got != row["sha256"]:
                failures.append({"path": row["path"], "error": "sha256_mismatch", "expected": row["sha256"], "got": got})
    return failures


def expand_config(run_root: Path) -> None:
    cfg_path = run_root / "configs" / "server_real_inputs.yaml"
    if not cfg_path.exists():
        return
    text = cfg_path.read_text()
    text = text.replace("${LEAKCERT_RUN_ROOT}", str(run_root))
    cfg_path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    run_root = Path(args.run_root).expanduser().resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(bundle, "r:gz") as tar:
            safe_extract(tar, tmp_path)
        payload = tmp_path / "payload"
        manifest_path = payload / "data_bundle_manifest.json"
        if not manifest_path.exists():
            raise SystemExit("bundle missing payload/data_bundle_manifest.json")
        manifest = json.loads(manifest_path.read_text())
        copy_payload(payload, run_root)

    expand_config(run_root)
    installed_manifest = run_root / "data_bundle_manifest.installed.json"
    manifest["installed_run_root"] = str(run_root)
    failures = verify(manifest, run_root)
    manifest["verification_failures"] = failures
    installed_manifest.write_text(json.dumps(manifest, indent=2) + "\n")

    result = {
        "run_root": str(run_root),
        "config": str(run_root / "configs" / "server_real_inputs.yaml"),
        "installed_manifest": str(installed_manifest),
        "verification_failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
