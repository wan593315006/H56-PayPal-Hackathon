"""Frozen K0 candidate contracts: Fact, provenance, candidate, and decision Fact."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from .canonical import ContractViolation, canonical_json, content_hash, require_text, require_text_tuple, require_timestamp


FACT_CONTRACT_ID = "K0:CANONICAL_FACT:V1"
FACT_TYPES = frozenset({"assertion", "correction", "invalidation", "decision", "transition_proposed"})
DECISIONS = frozenset({"ALLOW", "DENY", "MODIFY", "DEFER", "ISOLATE", "ESCALATE"})


@dataclass(frozen=True)
class VersionTuple:
    """Reserved now so K1 can derive State from a fixed interpretation contract."""

    compiler_version: str
    schema_version: str
    evidence_policy_version: str
    policy_version: str

    def __post_init__(self) -> None:
        for field in ("compiler_version", "schema_version", "evidence_policy_version", "policy_version"):
            require_text(getattr(self, field), field)

    def to_dict(self) -> dict[str, str]:
        return {
            "compiler_version": self.compiler_version,
            "schema_version": self.schema_version,
            "evidence_policy_version": self.evidence_policy_version,
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class FactProvenance:
    source_id: str
    object_id: str
    object_version: str
    environment_fingerprint: str
    schema_version: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("source_id", "object_id", "object_version", "environment_fingerprint", "schema_version"):
            require_text(getattr(self, field), field)
        object.__setattr__(
            self,
            "evidence_refs",
            require_text_tuple(self.evidence_refs, "evidence_refs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "object_id": self.object_id,
            "object_version": self.object_version,
            "environment_fingerprint": self.environment_fingerprint,
            "schema_version": self.schema_version,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class CandidateProposal:
    """A proposal is deliberately not an admitted Fact or a State mutation."""

    candidate_id: str
    subject_id: str
    requested_transition: str
    evidence_refs: tuple[str, ...]
    proposal_hash: str

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        requested_transition: str,
        evidence_refs: tuple[str, ...],
    ) -> "CandidateProposal":
        subject_id = require_text(subject_id, "subject_id")
        requested_transition = require_text(requested_transition, "requested_transition")
        evidence_refs = require_text_tuple(evidence_refs, "evidence_refs")
        core = {
            "contract_id": FACT_CONTRACT_ID,
            "subject_id": subject_id,
            "requested_transition": requested_transition,
            "evidence_refs": list(evidence_refs),
        }
        proposal_hash = content_hash(core)
        return cls(
            candidate_id=f"CAND:{proposal_hash[:24]}",
            subject_id=subject_id,
            requested_transition=requested_transition,
            evidence_refs=evidence_refs,
            proposal_hash=proposal_hash,
        )


@dataclass(frozen=True)
class Fact:
    fact_id: str
    fact_type: str
    subject_id: str
    occurred_at: str
    payload_json: str
    provenance: FactProvenance
    prior_fact_refs: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        fact_type: str,
        subject_id: str,
        occurred_at: str,
        payload: Mapping[str, Any],
        provenance: FactProvenance,
        prior_fact_refs: tuple[str, ...] = (),
    ) -> "Fact":
        fact_type = require_text(fact_type, "fact_type")
        if fact_type not in FACT_TYPES:
            raise ContractViolation(f"unsupported fact_type: {fact_type}")
        subject_id = require_text(subject_id, "subject_id")
        occurred_at = require_timestamp(occurred_at, "occurred_at")
        if not isinstance(payload, Mapping):
            raise ContractViolation("payload must be a mapping")
        prior_fact_refs = require_text_tuple(prior_fact_refs, "prior_fact_refs", allow_empty=True)
        if fact_type in {"correction", "invalidation"} and not prior_fact_refs:
            raise ContractViolation(f"{fact_type} requires prior_fact_refs")
        if fact_type not in {"correction", "invalidation"} and prior_fact_refs:
            raise ContractViolation(f"{fact_type} cannot carry prior_fact_refs")
        payload_json = canonical_json(dict(payload))
        core = {
            "contract_id": FACT_CONTRACT_ID,
            "fact_type": fact_type,
            "subject_id": subject_id,
            "occurred_at": occurred_at,
            "payload": json.loads(payload_json),
            "provenance": provenance.to_dict(),
            "prior_fact_refs": list(prior_fact_refs),
        }
        digest = content_hash(core)
        return cls(
            fact_id=f"FACT:{digest}",
            fact_type=fact_type,
            subject_id=subject_id,
            occurred_at=occurred_at,
            payload_json=payload_json,
            provenance=provenance,
            prior_fact_refs=prior_fact_refs,
        )

    def payload(self) -> dict[str, Any]:
        """Return a new decoded payload; callers cannot mutate stored Fact bytes."""
        return json.loads(self.payload_json)

    def canonical_core(self) -> dict[str, Any]:
        return {
            "contract_id": FACT_CONTRACT_ID,
            "fact_type": self.fact_type,
            "subject_id": self.subject_id,
            "occurred_at": self.occurred_at,
            "payload": self.payload(),
            "provenance": self.provenance.to_dict(),
            "prior_fact_refs": list(self.prior_fact_refs),
        }

    def verify(self) -> None:
        expected = f"FACT:{content_hash(self.canonical_core())}"
        if self.fact_id != expected:
            raise ContractViolation("fact_id does not match canonical content")


def build_decision_fact(
    *,
    candidate: CandidateProposal,
    decision: str,
    reason: str,
    occurred_at: str,
    provenance: FactProvenance,
    state_ref: str,
    constraint_refs: tuple[str, ...],
    policy_ref: str,
    authority_ref: str,
    version_tuple: VersionTuple,
) -> Fact:
    """Record a decision as a Fact without applying the requested transition."""
    decision = require_text(decision, "decision")
    if decision not in DECISIONS:
        raise ContractViolation(f"unsupported decision: {decision}")
    constraint_refs = require_text_tuple(constraint_refs, "constraint_refs")
    payload = {
        "candidate_id": candidate.candidate_id,
        "candidate_hash": candidate.proposal_hash,
        "requested_transition": candidate.requested_transition,
        "decision": decision,
        "reason": require_text(reason, "reason"),
        "state_ref": require_text(state_ref, "state_ref"),
        "evidence_refs": list(candidate.evidence_refs),
        "constraint_refs": list(constraint_refs),
        "policy_ref": require_text(policy_ref, "policy_ref"),
        "authority_ref": require_text(authority_ref, "authority_ref"),
        "version_tuple": version_tuple.to_dict(),
        "effect": "AUDIT_ONLY_NO_STATE_MUTATION",
    }
    return Fact.create(
        fact_type="decision",
        subject_id=candidate.subject_id,
        occurred_at=occurred_at,
        payload=payload,
        provenance=provenance,
    )
