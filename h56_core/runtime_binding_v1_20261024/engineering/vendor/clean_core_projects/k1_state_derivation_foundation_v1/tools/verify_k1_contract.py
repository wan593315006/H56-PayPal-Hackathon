"""Independent K1 verifier with K0 manifest precondition replay."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
K0_ROOT = PROJECT_ROOT.parent / "k0_canonical_fact_foundation_v1"
sys.path.insert(0, str(K0_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from k0_fact_foundation import Fact, FactHistory, FactProvenance, VersionTuple  # noqa: E402
from k0_fact_foundation.canonical import ContractViolation  # noqa: E402
from k1_state_derivation import SnapshotCache, StateCompilationError, StateCompiler  # noqa: E402


FORBIDDEN_PUBLIC_OPERATIONS = {"put", "update", "delete", "write_state", "set_state", "execute", "recover"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> FactProvenance:
    return FactProvenance(
        source_id="SRC:K1:VERIFIER",
        object_id="OBJ:K1:VERIFIER",
        object_version="1.0.0",
        environment_fingerprint="ENV:K1:VERIFIER",
        schema_version="K0:FACT:SCHEMA:V1",
        evidence_refs=("EVIDENCE:K1:VERIFIER",),
    )


def _version(policy: str = "POLICY:K1:V1") -> VersionTuple:
    return VersionTuple(
        compiler_version="K1:STATE_COMPILER:V1",
        schema_version="SCHEMA:K1:STATE:V1",
        evidence_policy_version="EVIDENCE_POLICY:K1:V1",
        policy_version=policy,
    )


def _fact(value: str) -> Fact:
    return Fact.create(
        fact_type="assertion",
        subject_id="SUBJECT:K1",
        occurred_at="2026-09-25T00:00:00Z",
        payload={"state_projection": {"lifecycle": value}},
        provenance=_provenance(),
    )


def _check(condition: bool, name: str, **detail: Any) -> dict[str, Any]:
    if not condition:
        raise ContractViolation(name)
    return {"name": name, "status": "PASS", **detail}


def _verify_k0_precondition() -> dict[str, Any]:
    manifest_path = K0_ROOT / "K0_PROJECT_MANIFEST.json"
    manifest_hash = _sha256(manifest_path)
    own_manifest = json.loads((PROJECT_ROOT / "K1_PROJECT_MANIFEST.json").read_text(encoding="utf-8"))
    expected_hash = str(own_manifest["predecessor"]["manifest_sha256"])
    if manifest_hash != expected_hash:
        raise ContractViolation("K0 manifest hash drifted; K1 precondition is no longer frozen")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failed = []
    for relative_path, expected_hash in manifest["artifact_hashes_sha256"].items():
        actual = _sha256(K0_ROOT / relative_path)
        if actual != expected_hash:
            failed.append(relative_path)
    if failed:
        raise ContractViolation("K0 artifact hash drift: " + ", ".join(failed))
    return {
        "name": "k0_precondition_manifest_and_artifacts_verified",
        "status": "PASS",
        "k0_manifest_sha256": manifest_hash,
        "expected_k0_manifest_sha256": expected_hash,
        "artifact_count": len(manifest["artifact_hashes_sha256"]),
    }


def _api_surface_check() -> dict[str, Any]:
    path = PROJECT_ROOT / "src" / "k1_state_derivation" / "state_compiler.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    public = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    forbidden = sorted(public & FORBIDDEN_PUBLIC_OPERATIONS)
    return {
        "name": "no_arbitrary_state_or_cache_writer_api",
        "status": "PASS" if not forbidden else "FAIL",
        "forbidden_public_operations_found": forbidden,
    }


def run_checks() -> list[dict[str, Any]]:
    checks = [_verify_k0_precondition()]
    history = FactHistory.empty().append(_fact("PENDING"))
    compiler = StateCompiler()
    first = compiler.compile(history, _version())
    second = compiler.compile(history, _version())
    checks.append(_check(
        first.snapshot_id == second.snapshot_id and first.state_by_subject() == second.state_by_subject(),
        "same_history_and_versions_replay_deterministically",
    ))
    changed_policy = compiler.compile(history, _version("POLICY:K1:V2"))
    checks.append(_check(
        first.snapshot_id != changed_policy.snapshot_id
        and first.state_by_subject() == changed_policy.state_by_subject(),
        "version_sensitive_interpretation_is_provenance_visible",
    ))

    malicious = Fact.create(
        fact_type="decision",
        subject_id="SUBJECT:K1",
        occurred_at="2026-09-25T00:01:00Z",
        payload={"decision": "DENY", "state_projection": {"lifecycle": "ACTIVE"}},
        provenance=_provenance(),
    )
    try:
        compiler.compile(FactHistory.empty().append(malicious), _version())
    except StateCompilationError:
        rejected = True
    else:
        rejected = False
    checks.append(_check(rejected, "candidate_decision_cannot_directly_project_state"))

    proposed_transition = Fact.create(
        fact_type="transition_proposed",
        subject_id="SUBJECT:K1",
        occurred_at="2026-09-25T00:01:30Z",
        payload={"state_projection": {"lifecycle": "ACTIVE"}},
        provenance=_provenance(),
    )
    try:
        compiler.compile(FactHistory.empty().append(proposed_transition), _version())
    except StateCompilationError:
        unknown_projection_rejected = True
    else:
        unknown_projection_rejected = False
    checks.append(_check(
        unknown_projection_rejected,
        "non_contributing_fact_cannot_silently_carry_state_projection",
    ))

    conflicting = FactHistory.empty().append(_fact("PENDING")).append(_fact("ACTIVE"))
    try:
        compiler.compile(conflicting, _version())
    except StateCompilationError:
        conflict_rejected = True
    else:
        conflict_rejected = False
    checks.append(_check(conflict_rejected, "ambiguous_active_projection_fails_closed"))

    cache = SnapshotCache(compiler)
    snapshot = cache.derive(history, _version())
    lookup = cache.lookup(history_id=history.history_id, version_tuple=_version())
    checks.append(_check(
        lookup is not None
        and lookup.snapshot_id == snapshot.snapshot_id
        and not hasattr(cache, "put")
        and not hasattr(cache, "write_state"),
        "snapshot_cache_is_derived_not_authoritative",
    ))
    checks.append(_api_surface_check())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checks = run_checks()
    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    source_files = [
        PROJECT_ROOT / "src" / "k1_state_derivation" / "__init__.py",
        PROJECT_ROOT / "src" / "k1_state_derivation" / "state_compiler.py",
    ]
    receipt = {
        "receipt_id": "K1_STATE_DERIVATION_FOUNDATION_CONTRACT_VALIDATION_V1",
        "status": status,
        "checks": checks,
        "source_hashes_sha256": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): _sha256(path)
            for path in source_files
        },
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "boundary": {
            "candidate_only": True,
            "authoritative_state_present": False,
            "runtime_write": False,
            "formal_mlm_write": False,
            "provider_or_mcp_call": False,
            "external_side_effect": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
