#!/usr/bin/env python3
"""Verify only the project manifest's managed file hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest_path = PROJECT_ROOT / "UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_MANIFEST.json"
    if not manifest_path.is_file():
        print("FAIL_URO_V1_1_MANIFEST_MISSING")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for item in manifest["managed_files"]:
        path = PROJECT_ROOT / item["path"]
        if not path.is_file():
            failures.append("missing:%s" % item["path"])
        elif digest(path) != item["sha256"]:
            failures.append("hash:%s" % item["path"])
    if failures:
        print("FAIL_URO_V1_1_MANIFEST")
        print("\n".join(failures))
        return 1
    print("PASS_URO_V1_1_MANIFEST:%d" % len(manifest["managed_files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
