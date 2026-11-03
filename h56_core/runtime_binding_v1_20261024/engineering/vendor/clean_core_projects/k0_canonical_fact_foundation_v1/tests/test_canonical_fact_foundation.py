from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from k0_fact_foundation import (  # noqa: E402
    CandidateProposal,
    CanonicalFactLedger,
    Fact,
    FactHistory,
    FactProvenance,
    StaleHistoryError,
    VersionTuple,
    build_decision_fact,
    derive_fact_resolution,
)
from k0_fact_foundation.canonical import ContractViolation  # noqa: E402


def provenance() -> FactProvenance:
    return FactProvenance(
        source_id="SRC:K0:TEST",
        object_id="OBJ:K0:ORDER:001",
        object_version="1.0.0",
        environment_fingerprint="ENV:K0:TEST:PYTHON",
        schema_version="K0:FACT:SCHEMA:V1",
        evidence_refs=("EVIDENCE:K0:TEST:001",),
    )


def assertion(payload=None) -> Fact:
    return Fact.create(
        fact_type="assertion",
        subject_id="ORDER:001",
        occurred_at="2026-09-25T00:00:00Z",
        payload=payload or {"paid_amount": 100, "total_amount": 100},
        provenance=provenance(),
    )


class CanonicalFactFoundationTests(unittest.TestCase):
    def test_canonical_payload_order_has_same_fact_identity(self):
        first = assertion({"a": 1, "b": {"x": 2, "y": 3}})
        second = assertion({"b": {"y": 3, "x": 2}, "a": 1})
        self.assertEqual(first.fact_id, second.fact_id)
        self.assertEqual(first.payload_json, second.payload_json)

    def test_reference_order_and_equivalent_utc_timestamp_are_normalized(self):
        left_provenance = FactProvenance(
            source_id="SRC:K0:TEST",
            object_id="OBJ:K0:ORDER:001",
            object_version="1.0.0",
            environment_fingerprint="ENV:K0:TEST:PYTHON",
            schema_version="K0:FACT:SCHEMA:V1",
            evidence_refs=("EVIDENCE:K0:B", "EVIDENCE:K0:A"),
        )
        right_provenance = FactProvenance(
            source_id="SRC:K0:TEST",
            object_id="OBJ:K0:ORDER:001",
            object_version="1.0.0",
            environment_fingerprint="ENV:K0:TEST:PYTHON",
            schema_version="K0:FACT:SCHEMA:V1",
            evidence_refs=("EVIDENCE:K0:A", "EVIDENCE:K0:B"),
        )
        left = Fact.create(
            fact_type="assertion",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T08:00:00+08:00",
            payload={"fact": "same"},
            provenance=left_provenance,
        )
        right = Fact.create(
            fact_type="assertion",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:00:00Z",
            payload={"fact": "same"},
            provenance=right_provenance,
        )
        self.assertEqual(left.fact_id, right.fact_id)
        self.assertEqual("2026-09-25T00:00:00Z", left.occurred_at)

    def test_timestamp_without_timezone_fails_closed(self):
        with self.assertRaises(ContractViolation):
            Fact.create(
                fact_type="assertion",
                subject_id="ORDER:001",
                occurred_at="2026-09-25T00:00:00",
                payload={"fact": "invalid"},
                provenance=provenance(),
            )

    def test_payload_copy_cannot_mutate_fact_bytes(self):
        fact = assertion({"nested": {"amount": 10}})
        copy = fact.payload()
        copy["nested"]["amount"] = 99
        self.assertEqual({"nested": {"amount": 10}}, fact.payload())
        fact.verify()

    def test_admitted_fact_fields_are_immutable(self):
        fact = assertion()
        with self.assertRaises(FrozenInstanceError):
            fact.subject_id = "ORDER:002"

    def test_non_json_payload_fails_closed(self):
        with self.assertRaises(ContractViolation):
            assertion({"bad": {1, 2}})

    def test_append_keeps_prior_history_value_and_rejects_duplicate(self):
        empty = FactHistory.empty()
        fact = assertion()
        next_history = empty.append(fact)
        self.assertEqual(0, len(empty.facts))
        self.assertEqual(1, len(next_history.facts))
        with self.assertRaises(ContractViolation):
            next_history.append(fact)

    def test_correction_appends_and_original_remains_superseded(self):
        original = assertion({"paid_amount": 110, "total_amount": 100})
        corrected = Fact.create(
            fact_type="correction",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:01:00Z",
            payload={"replacement_claim": {"paid_amount": 100, "total_amount": 100}},
            provenance=provenance(),
            prior_fact_refs=(original.fact_id,),
        )
        history = FactHistory.empty().append(original).append(corrected)
        resolution = derive_fact_resolution(history)
        self.assertEqual(2, len(history.facts))
        self.assertEqual("SUPERSEDED", resolution[original.fact_id]["status"])
        self.assertEqual("ACTIVE", resolution[corrected.fact_id]["status"])

    def test_invalidation_requires_existing_prior_fact(self):
        invalidation = Fact.create(
            fact_type="invalidation",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:02:00Z",
            payload={"reason": "source revoked"},
            provenance=provenance(),
            prior_fact_refs=("FACT:absent",),
        )
        with self.assertRaises(ContractViolation):
            FactHistory.empty().append(invalidation)

    def test_stale_writer_cannot_silently_append_to_old_history(self):
        ledger = CanonicalFactLedger()
        stale_id = ledger.read_history().history_id
        receipt = ledger.append(assertion({"event": 1}), expected_history_id=stale_id)
        self.assertEqual(0, receipt.ordinal)
        with self.assertRaises(StaleHistoryError):
            ledger.append(assertion({"event": 2}), expected_history_id=stale_id)
        self.assertEqual(1, len(ledger.read_history().facts))

    def test_no_public_update_or_delete_api_exists(self):
        ledger = CanonicalFactLedger()
        self.assertFalse(hasattr(ledger, "update"))
        self.assertFalse(hasattr(ledger, "delete"))

    def test_decision_fact_has_complete_trace_inputs(self):
        candidate = CandidateProposal.create(
            subject_id="ORDER:001",
            requested_transition="ORDER:001 -> ACTIVE",
            evidence_refs=("EVIDENCE:K0:CANDIDATE:001",),
        )
        decision = build_decision_fact(
            candidate=candidate,
            decision="DENY",
            reason="missing_authority",
            occurred_at="2026-09-25T00:03:00Z",
            provenance=provenance(),
            state_ref="STATE:K1:NOT_IMPLEMENTED",
            constraint_refs=("CONSTRAINT:AUTHORITY_REQUIRED",),
            policy_ref="POLICY:K0:CANDIDATE_ONLY",
            authority_ref="AUTHORITY:NONE",
            version_tuple=VersionTuple("K1:none", "K0:1", "K0:1", "K0:1"),
        )
        payload = decision.payload()
        self.assertEqual("DENY", payload["decision"])
        self.assertEqual("AUDIT_ONLY_NO_STATE_MUTATION", payload["effect"])
        self.assertEqual(candidate.proposal_hash, payload["candidate_hash"])

    def test_rejected_candidate_non_interference_is_fact_only(self):
        ledger = CanonicalFactLedger()
        candidate = CandidateProposal.create(
            subject_id="ORDER:001",
            requested_transition="ORDER:001 -> ACTIVE",
            evidence_refs=("EVIDENCE:K0:CANDIDATE:002",),
        )
        decision = build_decision_fact(
            candidate=candidate,
            decision="DENY",
            reason="authority_pending",
            occurred_at="2026-09-25T00:04:00Z",
            provenance=provenance(),
            state_ref="STATE:K1:NOT_IMPLEMENTED",
            constraint_refs=("CONSTRAINT:NO_DIRECT_STATE_WRITE",),
            policy_ref="POLICY:K0:CANDIDATE_ONLY",
            authority_ref="AUTHORITY:PENDING",
            version_tuple=VersionTuple("K1:none", "K0:1", "K0:1", "K0:1"),
        )
        before = ledger.read_history()
        ledger.append(decision, expected_history_id=before.history_id)
        after = ledger.read_history()
        self.assertEqual(0, len(before.facts))
        self.assertEqual(1, len(after.facts))
        self.assertEqual("decision", after.facts[0].fact_type)
        self.assertNotIn("transition_applied", after.facts[0].payload())
        self.assertFalse(hasattr(ledger, "write_state"))

    def test_history_replay_and_resolution_are_deterministic(self):
        original = assertion({"value": 1})
        invalidation = Fact.create(
            fact_type="invalidation",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:05:00Z",
            payload={"reason": "invalid source"},
            provenance=provenance(),
            prior_fact_refs=(original.fact_id,),
        )
        history = FactHistory.empty().append(original).append(invalidation)
        replay = FactHistory.empty().append(original).append(invalidation)
        self.assertEqual(history.history_id, replay.history_id)
        self.assertEqual(derive_fact_resolution(history), derive_fact_resolution(replay))


if __name__ == "__main__":
    unittest.main()
