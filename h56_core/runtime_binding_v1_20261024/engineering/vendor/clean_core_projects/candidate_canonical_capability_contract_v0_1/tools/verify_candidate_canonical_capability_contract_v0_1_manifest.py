"""Verify C1's derived source-manifest hashes without running project code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("project_id") != "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1":
        print("PROJECT_ID_MISMATCH")
        return 2
    for entry in manifest.get("source_files", []):
        path = ROOT / entry["path"]
        if not path.is_file() or digest(path) != entry["sha256"]:
            print("PROJECT_MANIFEST_HASH_MISMATCH:%s" % entry["path"])
            return 2
    print("PASS_C1_PROJECT_MANIFEST:%d" % len(manifest.get("source_files", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
