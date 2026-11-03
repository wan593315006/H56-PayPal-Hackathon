"""Independent, standard-library K0 contract verifier.

It validates the candidate foundation without importing legacy Five-Body code,
opening a Runtime, or writing anywhere except an explicitly supplied receipt.
"""

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
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from k0_fact_foundation import (  # noqa: E402
    CandidateProposal,
    CanonicalFactLedger,
    Fact,
    FactHistory,
    FactProvenance,
    VersionTuple,
    build_decision_fact,
    derive_fact_resolution,
)
from k0_fact_foundation.canonical import ContractViolation  # noqa: E402


FORBIDDEN_PUBLIC_OPERATIONS = {"update", "delete", "write_state", "set_state", "execute", "recover"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance() -> FactProvenance:
    return FactProvenance(
        source_id="SRC:K0:VERIFIER",
        object_id="OBJ:K0:VERIFIER",
        object_version="1.0.0",
        environment_fingerprint="ENV:K0:VERIFIER",
        schema_version="K0:FACT:SCHEMA:V1",
        evidence_refs=("EVIDENCE:K0:VERIFIER",),
    )


def _assert(condition: bool, label: str) -> dict[str, Any]:
    if not condition:
        raise ContractViolation(label)
    return {"name": label, "status": "PASS"}


def _api_surface_check() -> dict[str, Any]:
    path = PROJECT_ROOT / "src" / "k0_fact_foundation" / "history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    public = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    forbidden = sorted(public & FORBIDDEN_PUBLIC_OPERATIONS)
    return {
        "name": "no_arbitrary_history_or_state_write_api",
        "status": "PASS" if not forbidden else "FAIL",
        "forbidden_public_operations_found": forbidden,
    }


def run_checks() -> list[dict[str, Any]]:
    provenance = _provenance()
    left = Fact.create(
        fact_type="assertion",
        subject_id="SUBJECT:K0",
        occurred_at="2026-09-25T00:00:00Z",
        payload={"a": 1, "nested": {"b": 2}},
        provenance=provenance,
    )
    right = Fact.create(
        fact_type="assertion",
        subject_id="SUBJECT:K0",
        occurred_at="2026-09-25T00:00:00Z",
        payload={"nested": {"b": 2}, "a": 1},
        provenance=provenance,
    )
    checks = [_assert(left.fact_id == right.fact_id, "canonical_fact_identity_is_deterministic")]

    history = FactHistory.empty().append(left)
    try:
        history.append(left)
    except ContractViolation:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    checks.append(_assert(duplicate_rejected and len(history.facts) == 1, "admitted_fact_cannot_be_overwritten"))

    correction = Fact.create(
        fact_type="correction",
        subject_id="SUBJECT:K0",
        occurred_at="2026-09-25T00:01:00Z",
        payload={"replacement_claim": {"a": 2}},
        provenance=provenance,
        prior_fact_refs=(left.fact_id,),
    )
    amended = history.append(correction)
    resolution = derive_fact_resolution(amended)
    checks.append(_assert(
        len(amended.facts) == 2 and resolution[left.fact_id]["status"] == "SUPERSEDED",
        "correction_is_new_fact_not_overwrite",
    ))

    ledger = CanonicalFactLedger()
    stale_history_id = ledger.read_history().history_id
    ledger.append(left, expected_history_id=stale_history_id)
    try:
        ledger.append(right, expected_history_id=stale_history_id)
    except ContractViolation:
        stale_rejected = True
    else:
        stale_rejected = False
    checks.append(_assert(stale_rejected, "stale_writer_fails_closed"))

    candidate = CandidateProposal.create(
        subject_id="SUBJECT:K0",
        requested_transition="SUBJECT:K0 -> ACTIVE",
        evidence_refs=("EVIDENCE:K0:CANDIDATE",),
    )
    denial = build_decision_fact(
        candidate=candidate,
        decision="DENY",
        reason="authority_pending",
        occurred_at="2026-09-25T00:02:00Z",
        provenance=provenance,
        state_ref="STATE:K1:NOT_IMPLEMENTED",
        constraint_refs=("CONSTRAINT:NO_DIRECT_STATE_WRITE",),
        policy_ref="POLICY:K0:CANDIDATE_ONLY",
        authority_ref="AUTHORITY:PENDING",
        version_tuple=VersionTuple("K1:none", "K0:1", "K0:1", "K0:1"),
    )
    denial_payload = denial.payload()
    checks.append(_assert(
        denial.fact_type == "decision"
        and denial_payload["effect"] == "AUDIT_ONLY_NO_STATE_MUTATION"
        and "transition_applied" not in denial_payload,
        "rejected_candidate_has_no_direct_state_effect",
    ))
    checks.append(_api_surface_check())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checks = run_checks()
    status = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    source_files = [
        PROJECT_ROOT / "src" / "k0_fact_foundation" / "canonical.py",
        PROJECT_ROOT / "src" / "k0_fact_foundation" / "contracts.py",
        PROJECT_ROOT / "src" / "k0_fact_foundation" / "history.py",
    ]
    receipt = {
        "receipt_id": "K0_CANONICAL_FACT_FOUNDATION_CONTRACT_VALIDATION_V1",
        "status": status,
        "checks": checks,
        "source_hashes_sha256": {str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): _sha256(path) for path in source_files},
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
