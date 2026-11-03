"""Fail closed if C1's declared C0 audit predecessor has drifted."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
BINDING_FILE = ROOT / "C1_C0_AUDIT_BINDING_V1.json"


class C0BindingError(ValueError):
    """Raised when C0's frozen audit source cannot be independently replayed."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_binding() -> Mapping[str, Any]:
    return json.loads(BINDING_FILE.read_text(encoding="utf-8"))


def verify_c0_binding(binding: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    value = dict(binding or load_binding())
    path = REPOSITORY / value["audit_manifest_path"]
    if not path.is_file():
        raise C0BindingError("C0_AUDIT_MANIFEST_MISSING")
    if _digest(path) != value["audit_manifest_sha256"]:
        raise C0BindingError("C0_AUDIT_MANIFEST_HASH_DRIFT")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("audit_id") != value["audit_id"]:
        raise C0BindingError("C0_AUDIT_ID_MISMATCH")
    if manifest.get("status") != value["required_status"]:
        raise C0BindingError("C0_AUDIT_STATUS_MISMATCH")
    if manifest.get("verdict", {}).get("next_gate") != value["required_next_gate"]:
        raise C0BindingError("C0_AUDIT_NEXT_GATE_MISMATCH")
    files = manifest.get("managed_files")
    if not isinstance(files, list) or not files:
        raise C0BindingError("C0_AUDIT_MANAGED_FILES_MISSING")
    audit_root = path.parent
    for entry in files:
        candidate = audit_root / entry["path"]
        if not candidate.is_file() or _digest(candidate) != entry["sha256"]:
            raise C0BindingError("C0_AUDIT_MANAGED_FILE_DRIFT:%s" % entry["path"])
    return {"result": "PASS_C0_AUDIT_BINDING", "managed_file_count": len(files)}


if __name__ == "__main__":
    result = verify_c0_binding()
    print("%s:%d" % (result["result"], result["managed_file_count"]))
