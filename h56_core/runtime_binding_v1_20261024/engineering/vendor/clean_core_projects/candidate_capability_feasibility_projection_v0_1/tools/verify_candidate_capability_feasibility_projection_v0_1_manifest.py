"""Verify C2's project-manifest source hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_PROJECT_MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> int:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if value.get("project_id") != "CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1":
        print("PROJECT_ID_MISMATCH")
        return 2
    for item in value.get("source_files", []):
        path = ROOT / item["path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            print("PROJECT_MANIFEST_HASH_MISMATCH:%s" % item["path"])
            return 2
    print("PASS_C2_PROJECT_MANIFEST:%d" % len(value.get("source_files", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
