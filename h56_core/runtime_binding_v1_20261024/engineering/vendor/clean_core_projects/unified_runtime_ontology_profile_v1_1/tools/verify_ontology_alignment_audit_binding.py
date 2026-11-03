#!/usr/bin/env python3
"""Verify the V1.1 recommendation audit by raw audit-manifest identity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
AUDIT_ROOT = REPO_ROOT / "project_control_plane" / "AUDITS" / "UNIFIED_RUNTIME_ONTOLOGY_ALIGNMENT_AND_EVOLUTION_AUDIT_V1_20261004"
EXPECTED_AUDIT_MANIFEST_SHA256 = "485f260a4eb314e5470aad57806b5418a1e786b65f8825ccbf20b8125fa92bc4"


class AuditBindingError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_audit_binding(expected: str = EXPECTED_AUDIT_MANIFEST_SHA256):
    manifest = AUDIT_ROOT / "AUDIT_MANIFEST.json"
    terms = AUDIT_ROOT / "RECOMMENDATIONS" / "CORE_AND_EXTENSION_TERMS.json"
    relation = AUDIT_ROOT / "RECOMMENDATIONS" / "RELATION_VOCABULARY.md"
    version = AUDIT_ROOT / "RECOMMENDATIONS" / "VERSION_AND_MIGRATION_RULES.md"
    for path in (manifest, terms, relation, version):
        if not path.is_file():
            raise AuditBindingError("ONTOLOGY_AUDIT_ARTIFACT_MISSING:%s" % path.name)
    if digest(manifest) != expected:
        raise AuditBindingError("ONTOLOGY_AUDIT_MANIFEST_HASH_DRIFT")
    payload = json.loads(terms.read_text(encoding="utf-8"))
    if payload.get("status") != "PROPOSED_FOR_CONTROLLER_PROFILE_REVIEW_ONLY":
        raise AuditBindingError("ONTOLOGY_AUDIT_TERM_STATUS_DRIFT")
    if payload.get("canonical_id_convention", {}).get("core") != "uro:<Term>":
        raise AuditBindingError("ONTOLOGY_AUDIT_ID_CONVENTION_DRIFT")
    return {"result": "PASS_ONTOLOGY_ALIGNMENT_AUDIT_BINDING", "manifest_sha256": expected}


def main() -> int:
    try:
        result = verify_audit_binding()
    except AuditBindingError as exc:
        print("FAIL_ONTOLOGY_ALIGNMENT_AUDIT_BINDING:%s" % exc)
        return 1
    print("%s:%s" % (result["result"], result["manifest_sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
