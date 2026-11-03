"""Pure, content-bound candidate feasibility data contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Tuple


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Z][A-Z0-9:_-]{2,127}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$")
_GIT = re.compile(r"^[0-9a-f]{40}$")


class CapabilityFeasibilityError(ValueError):
    """Raised for malformed or tampered candidate projection inputs."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _exact(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if not isinstance(value, Mapping):
        raise CapabilityFeasibilityError(label + "_NOT_A_MAPPING")
    actual = frozenset(value.keys())
    if actual == expected:
        return
    unknown = actual - expected
    if unknown:
        raise CapabilityFeasibilityError(label + "_UNKNOWN_FIELD:" + ",".join(sorted(unknown)))
    raise CapabilityFeasibilityError(label + "_MISSING_FIELD:" + ",".join(sorted(expected - actual)))


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise CapabilityFeasibilityError(label + "_INVALID_IDENTITY")
    return value


def _version(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise CapabilityFeasibilityError(label + "_INVALID_VERSION")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CapabilityFeasibilityError(label + "_INVALID_SHA256")
    return value


def _sequence(value: Any, label: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise CapabilityFeasibilityError(label + "_INVALID_SEQUENCE")
    return tuple(value)


@dataclass(frozen=True)
class CapabilityCatalogReference:
    """Public C1-shaped catalog identity claim; never a registry client."""

    catalog_id: str
    catalog_version: str
    catalog_hash: str
    contract_project_id: str
    contract_commit: str
    contract_manifest_sha256: str
    capability_id: str
    definition_hash: str
    reference_hash: str

    _FIELDS = frozenset({"catalog_id", "catalog_version", "catalog_hash", "contract_project_id", "contract_commit", "contract_manifest_sha256", "capability_id", "definition_hash", "reference_hash"})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CapabilityCatalogReference":
        _exact(value, cls._FIELDS, "C1_CATALOG_REFERENCE")
        if value["contract_project_id"] != "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1":
            raise CapabilityFeasibilityError("C1_CATALOG_REFERENCE_PROJECT_MISMATCH")
        if not isinstance(value["contract_commit"], str) or not _GIT.fullmatch(value["contract_commit"]):
            raise CapabilityFeasibilityError("C1_CATALOG_REFERENCE_INVALID_COMMIT")
        body = {
            "catalog_id": _identity(value["catalog_id"], "C1_CATALOG"),
            "catalog_version": _version(value["catalog_version"], "C1_CATALOG"),
            "catalog_hash": _hash(value["catalog_hash"], "C1_CATALOG"),
            "contract_project_id": value["contract_project_id"],
            "contract_commit": value["contract_commit"],
            "contract_manifest_sha256": _hash(value["contract_manifest_sha256"], "C1_CONTRACT_MANIFEST"),
            "capability_id": _identity(value["capability_id"], "C1_CAPABILITY"),
            "definition_hash": _hash(value["definition_hash"], "C1_DEFINITION"),
        }
        supplied = _hash(value["reference_hash"], "C1_CATALOG_REFERENCE")
        if supplied != canonical_sha256(body):
            raise CapabilityFeasibilityError("C1_CATALOG_REFERENCE_HASH_MISMATCH")
        return cls(reference_hash=supplied, **body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {field: getattr(self, field) for field in self._FIELDS if field != "reference_hash"}

    def verify(self) -> None:
        if self.reference_hash != canonical_sha256(self.body_mapping()):
            raise CapabilityFeasibilityError("C1_CATALOG_REFERENCE_IDENTITY_DRIFT")


@dataclass(frozen=True)
class CapabilityAvailabilityAssertion:
    """A candidate availability claim, not proof of a live capability."""

    capability_id: str
    definition_hash: str
    availability_state: str
    allowed_task_kinds: Tuple[str, ...]
    allowed_state_patterns: Tuple[str, ...]
    allowed_method_ids: Tuple[str, ...]
    minimum_budget_units: int
    required_evidence_state: str
    assertion_hash: str

    _FIELDS = frozenset({"capability_id", "definition_hash", "availability_state", "allowed_task_kinds", "allowed_state_patterns", "allowed_method_ids", "minimum_budget_units", "required_evidence_state", "assertion_hash"})
    _AVAILABILITY = frozenset({"DECLARED_AVAILABLE", "DECLARED_UNAVAILABLE", "DECLARED_UNKNOWN"})
    _EVIDENCE = frozenset({"SUFFICIENT", "INSUFFICIENT", "UNKNOWN"})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CapabilityAvailabilityAssertion":
        _exact(value, cls._FIELDS, "AVAILABILITY_ASSERTION")
        if value["availability_state"] not in cls._AVAILABILITY:
            raise CapabilityFeasibilityError("AVAILABILITY_ASSERTION_INVALID_STATE")
        if value["required_evidence_state"] not in cls._EVIDENCE:
            raise CapabilityFeasibilityError("AVAILABILITY_ASSERTION_INVALID_EVIDENCE_STATE")
        if not isinstance(value["minimum_budget_units"], int) or value["minimum_budget_units"] < 0:
            raise CapabilityFeasibilityError("AVAILABILITY_ASSERTION_INVALID_BUDGET")
        body = {
            "capability_id": _identity(value["capability_id"], "AVAILABILITY_CAPABILITY"),
            "definition_hash": _hash(value["definition_hash"], "AVAILABILITY_DEFINITION"),
            "availability_state": value["availability_state"],
            "allowed_task_kinds": _sequence(value["allowed_task_kinds"], "AVAILABILITY_TASK_KINDS"),
            "allowed_state_patterns": _sequence(value["allowed_state_patterns"], "AVAILABILITY_STATE_PATTERNS"),
            "allowed_method_ids": _sequence(value["allowed_method_ids"], "AVAILABILITY_METHOD_IDS"),
            "minimum_budget_units": value["minimum_budget_units"],
            "required_evidence_state": value["required_evidence_state"],
        }
        supplied = _hash(value["assertion_hash"], "AVAILABILITY_ASSERTION")
        if supplied != canonical_sha256(body):
            raise CapabilityFeasibilityError("AVAILABILITY_ASSERTION_HASH_MISMATCH")
        return cls(assertion_hash=supplied, **body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {field: getattr(self, field) for field in self._FIELDS if field != "assertion_hash"}

    def verify(self) -> None:
        if self.assertion_hash != canonical_sha256(self.body_mapping()):
            raise CapabilityFeasibilityError("AVAILABILITY_ASSERTION_IDENTITY_DRIFT")


@dataclass(frozen=True)
class FeasibilityContext:
    """Frozen candidate snapshots for one pure feasibility projection."""

    task_kind: str
    task_snapshot_hash: str
    state_pattern: str
    state_snapshot_hash: str
    method_id: str
    method_hash: str
    policy_state: str
    policy_snapshot_hash: str
    authority_state: str
    authority_snapshot_hash: str
    budget_available_units: int
    budget_snapshot_hash: str
    evidence_state: str
    evidence_snapshot_hash: str
    context_hash: str

    _FIELDS = frozenset({"task_kind", "task_snapshot_hash", "state_pattern", "state_snapshot_hash", "method_id", "method_hash", "policy_state", "policy_snapshot_hash", "authority_state", "authority_snapshot_hash", "budget_available_units", "budget_snapshot_hash", "evidence_state", "evidence_snapshot_hash", "context_hash"})
    _POLICY = frozenset({"DECLARED_ALLOWED", "DECLARED_DENIED", "DECLARED_UNKNOWN"})
    _AUTHORITY = frozenset({"DECLARED_SUFFICIENT", "DECLARED_INSUFFICIENT", "DECLARED_UNKNOWN"})
    _EVIDENCE = frozenset({"SUFFICIENT", "INSUFFICIENT", "UNKNOWN"})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FeasibilityContext":
        _exact(value, cls._FIELDS, "FEASIBILITY_CONTEXT")
        if value["policy_state"] not in cls._POLICY:
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_INVALID_POLICY_STATE")
        if value["authority_state"] not in cls._AUTHORITY:
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_INVALID_AUTHORITY_STATE")
        if value["evidence_state"] not in cls._EVIDENCE:
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_INVALID_EVIDENCE_STATE")
        if not isinstance(value["budget_available_units"], int) or value["budget_available_units"] < 0:
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_INVALID_BUDGET")
        body = {
            "task_kind": _identity(value["task_kind"], "TASK_KIND"),
            "task_snapshot_hash": _hash(value["task_snapshot_hash"], "TASK_SNAPSHOT"),
            "state_pattern": _identity(value["state_pattern"], "STATE_PATTERN"),
            "state_snapshot_hash": _hash(value["state_snapshot_hash"], "STATE_SNAPSHOT"),
            "method_id": _identity(value["method_id"], "METHOD"),
            "method_hash": _hash(value["method_hash"], "METHOD"),
            "policy_state": value["policy_state"],
            "policy_snapshot_hash": _hash(value["policy_snapshot_hash"], "POLICY_SNAPSHOT"),
            "authority_state": value["authority_state"],
            "authority_snapshot_hash": _hash(value["authority_snapshot_hash"], "AUTHORITY_SNAPSHOT"),
            "budget_available_units": value["budget_available_units"],
            "budget_snapshot_hash": _hash(value["budget_snapshot_hash"], "BUDGET_SNAPSHOT"),
            "evidence_state": value["evidence_state"],
            "evidence_snapshot_hash": _hash(value["evidence_snapshot_hash"], "EVIDENCE_SNAPSHOT"),
        }
        supplied = _hash(value["context_hash"], "FEASIBILITY_CONTEXT")
        if supplied != canonical_sha256(body):
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_HASH_MISMATCH")
        return cls(context_hash=supplied, **body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {field: getattr(self, field) for field in self._FIELDS if field != "context_hash"}

    def verify(self) -> None:
        if self.context_hash != canonical_sha256(self.body_mapping()):
            raise CapabilityFeasibilityError("FEASIBILITY_CONTEXT_IDENTITY_DRIFT")


@dataclass(frozen=True)
class FeasibilityProjection:
    """Traceable candidate result that cannot grant operational rights."""

    capability_id: str
    catalog_reference_hash: str
    availability_assertion_hash: str
    context_hash: str
    decision: str
    reason_codes: Tuple[str, ...]
    candidate_planning_only: bool
    authority_granted: bool
    execution_permitted: bool
    projection_hash: str

    _DECISIONS = frozenset({"FEASIBLE", "INFEASIBLE", "DEFER", "NEED_MORE_EVIDENCE"})

    @classmethod
    def create(cls, catalog: CapabilityCatalogReference, assertion: CapabilityAvailabilityAssertion, context: FeasibilityContext, decision: str, reason_codes: Tuple[str, ...]) -> "FeasibilityProjection":
        if decision not in cls._DECISIONS or not reason_codes:
            raise CapabilityFeasibilityError("FEASIBILITY_PROJECTION_INVALID_DECISION")
        body = {
            "capability_id": catalog.capability_id,
            "catalog_reference_hash": catalog.reference_hash,
            "availability_assertion_hash": assertion.assertion_hash,
            "context_hash": context.context_hash,
            "decision": decision,
            "reason_codes": reason_codes,
            "candidate_planning_only": True,
            "authority_granted": False,
            "execution_permitted": False,
        }
        return cls(projection_hash=canonical_sha256(body), **body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {
            "capability_id": self.capability_id,
            "catalog_reference_hash": self.catalog_reference_hash,
            "availability_assertion_hash": self.availability_assertion_hash,
            "context_hash": self.context_hash,
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "candidate_planning_only": self.candidate_planning_only,
            "authority_granted": self.authority_granted,
            "execution_permitted": self.execution_permitted,
        }

    def verify(self) -> None:
        if self.projection_hash != canonical_sha256(self.body_mapping()):
            raise CapabilityFeasibilityError("FEASIBILITY_PROJECTION_IDENTITY_DRIFT")
        if not self.candidate_planning_only or self.authority_granted or self.execution_permitted:
            raise CapabilityFeasibilityError("FEASIBILITY_PROJECTION_BOUNDARY_DRIFT")


@dataclass(frozen=True)
class CandidateCapabilityFeasibleSet:
    """An ordered, trace-preserving candidate subset for one frozen context."""

    context_hash: str
    projection_hashes: Tuple[str, ...]
    feasible_capability_ids: Tuple[str, ...]
    candidate_planning_only: bool
    authority_granted: bool
    execution_permitted: bool
    set_hash: str

    @classmethod
    def create(cls, projections: Tuple[FeasibilityProjection, ...]) -> "CandidateCapabilityFeasibleSet":
        if not projections:
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_PROJECTIONS_REQUIRED")
        for projection in projections:
            projection.verify()
        capability_ids = tuple(projection.capability_id for projection in projections)
        if capability_ids != tuple(sorted(capability_ids)):
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_PROJECTIONS_NOT_SORTED")
        if len(capability_ids) != len(set(capability_ids)):
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_DUPLICATE_CAPABILITY_ID")
        context_hashes = {projection.context_hash for projection in projections}
        if len(context_hashes) != 1:
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_CONTEXT_MISMATCH")
        body = {
            "context_hash": projections[0].context_hash,
            "projection_hashes": tuple(projection.projection_hash for projection in projections),
            "feasible_capability_ids": tuple(
                projection.capability_id for projection in projections if projection.decision == "FEASIBLE"
            ),
            "candidate_planning_only": True,
            "authority_granted": False,
            "execution_permitted": False,
        }
        return cls(set_hash=canonical_sha256(body), **body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {
            "context_hash": self.context_hash,
            "projection_hashes": self.projection_hashes,
            "feasible_capability_ids": self.feasible_capability_ids,
            "candidate_planning_only": self.candidate_planning_only,
            "authority_granted": self.authority_granted,
            "execution_permitted": self.execution_permitted,
        }

    def verify(self) -> None:
        if self.set_hash != canonical_sha256(self.body_mapping()):
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_IDENTITY_DRIFT")
        if not self.candidate_planning_only or self.authority_granted or self.execution_permitted:
            raise CapabilityFeasibilityError("CAPABILITY_FEASIBLE_SET_BOUNDARY_DRIFT")
