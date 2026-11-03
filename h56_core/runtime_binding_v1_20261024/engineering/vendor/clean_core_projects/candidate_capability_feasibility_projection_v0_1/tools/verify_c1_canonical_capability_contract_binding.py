"""Fail closed if C2's frozen C1 source contract has drifted."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
BINDING_FILE = ROOT / "C2_C1_CONTRACT_BINDING_V1.json"


class C1BindingError(ValueError):
    """Raised when the C1 contract source cannot be replayed exactly."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_binding() -> Mapping[str, Any]:
    return json.loads(BINDING_FILE.read_text(encoding="utf-8"))


def verify_c1_binding(binding: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    value = dict(binding or load_binding())
    manifest_path = REPOSITORY / value["project_manifest_path"]
    if not manifest_path.is_file():
        raise C1BindingError("C1_PROJECT_MANIFEST_MISSING")
    if _digest(manifest_path) != value["project_manifest_sha256"]:
        raise C1BindingError("C1_PROJECT_MANIFEST_HASH_DRIFT")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("project_id") != value["project_id"] or manifest.get("status") != value["required_status"]:
        raise C1BindingError("C1_PROJECT_MANIFEST_IDENTITY_DRIFT")
    source_root = manifest_path.parent
    files = manifest.get("source_files")
    if not isinstance(files, list) or not files:
        raise C1BindingError("C1_PROJECT_MANIFEST_FILES_MISSING")
    for entry in files:
        source = source_root / entry["path"]
        if not source.is_file() or _digest(source) != entry["sha256"]:
            raise C1BindingError("C1_PROJECT_MANIFEST_SOURCE_DRIFT:%s" % entry["path"])
    return {"result": "PASS_C1_CONTRACT_BINDING", "managed_file_count": len(files)}


if __name__ == "__main__":
    result = verify_c1_binding()
    print("%s:%d" % (result["result"], result["managed_file_count"]))
