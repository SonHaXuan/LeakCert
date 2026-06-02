#!/usr/bin/env python3
"""Write a JSON manifest with file sizes and SHA-256 hashes for a run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--output", default="manifest.json")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != args.output:
            rows.append({
                "path": str(path.relative_to(run_dir)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            })
    (run_dir / args.output).write_text(json.dumps(rows, indent=2))
    print(json.dumps({"run_dir": str(run_dir), "files": len(rows), "manifest": str(run_dir / args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
