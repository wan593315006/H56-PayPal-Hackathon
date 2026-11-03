from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
K0_ROOT = PROJECT_ROOT.parent / "k0_canonical_fact_foundation_v1"
sys.path.insert(0, str(K0_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from k0_fact_foundation import (  # noqa: E402
    CandidateProposal,
    Fact,
    FactHistory,
    FactProvenance,
    VersionTuple,
    build_decision_fact,
)
from k0_fact_foundation.canonical import ContractViolation  # noqa: E402
from k1_state_derivation import SnapshotCache, StateCompilationError, StateCompiler  # noqa: E402


COMPILER_VERSION = "K1:STATE_COMPILER:V1"


def provenance() -> FactProvenance:
    return FactProvenance(
        source_id="SRC:K1:TEST",
        object_id="OBJ:K1:ORDER:001",
        object_version="1.0.0",
        environment_fingerprint="ENV:K1:TEST",
        schema_version="K0:FACT:SCHEMA:V1",
        evidence_refs=("EVIDENCE:K1:TEST",),
    )


def version_tuple(*, policy: str = "POLICY:K1:V1", compiler: str = COMPILER_VERSION) -> VersionTuple:
    return VersionTuple(
        compiler_version=compiler,
        schema_version="SCHEMA:K1:STATE:V1",
        evidence_policy_version="EVIDENCE_POLICY:K1:V1",
        policy_version=policy,
    )


def state_fact(subject: str, projection: dict, *, fact_type: str = "assertion", prior=()) -> Fact:
    return Fact.create(
        fact_type=fact_type,
        subject_id=subject,
        occurred_at="2026-09-25T00:00:00Z",
        payload={"state_projection": projection},
        provenance=provenance(),
        prior_fact_refs=prior,
    )


class StateDerivationFoundationTests(unittest.TestCase):
    def test_same_history_and_version_tuple_replay_to_same_snapshot(self):
        history = FactHistory.empty().append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        compiler = StateCompiler()
        first = compiler.compile(history, version_tuple())
        second = compiler.compile(history, version_tuple())
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.state_by_subject(), second.state_by_subject())
        self.assertEqual(history.history_id, first.history_id)

    def test_snapshot_records_complete_version_provenance(self):
        history = FactHistory.empty().append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        snapshot = StateCompiler().compile(history, version_tuple())
        provenance_record = snapshot.provenance()
        self.assertEqual(COMPILER_VERSION, provenance_record["compiler_version"])
        self.assertEqual("SCHEMA:K1:STATE:V1", provenance_record["schema_version"])
        self.assertEqual("EVIDENCE_POLICY:K1:V1", provenance_record["evidence_policy_version"])
        self.assertEqual("POLICY:K1:V1", provenance_record["policy_version"])

    def test_version_change_is_visible_even_when_state_content_matches(self):
        history = FactHistory.empty().append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        compiler = StateCompiler()
        baseline = compiler.compile(history, version_tuple(policy="POLICY:K1:V1"))
        reinterpreted = compiler.compile(history, version_tuple(policy="POLICY:K1:V2"))
        self.assertEqual(baseline.state_by_subject(), reinterpreted.state_by_subject())
        self.assertNotEqual(baseline.snapshot_id, reinterpreted.snapshot_id)
        self.assertNotEqual(
            baseline.provenance()["policy_version"],
            reinterpreted.provenance()["policy_version"],
        )

    def test_compiler_version_mismatch_fails_closed(self):
        history = FactHistory.empty()
        with self.assertRaises(StateCompilationError):
            StateCompiler().compile(history, version_tuple(compiler="K1:STATE_COMPILER:V2"))

    def test_correction_replaces_projection_only_through_history_resolution(self):
        original = state_fact("ORDER:001", {"lifecycle": "PENDING"})
        correction = state_fact(
            "ORDER:001",
            {"lifecycle": "ACTIVE"},
            fact_type="correction",
            prior=(original.fact_id,),
        )
        history = FactHistory.empty().append(original).append(correction)
        snapshot = StateCompiler().compile(history, version_tuple())
        self.assertEqual({"ORDER:001": {"lifecycle": "ACTIVE"}}, snapshot.state_by_subject())
        self.assertEqual((correction.fact_id,), snapshot.contributing_fact_ids)

    def test_invalidation_removes_projection_without_mutating_original_fact(self):
        original = state_fact("ORDER:001", {"lifecycle": "PENDING"})
        invalidation = Fact.create(
            fact_type="invalidation",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:01:00Z",
            payload={"reason": "evidence revoked"},
            provenance=provenance(),
            prior_fact_refs=(original.fact_id,),
        )
        history = FactHistory.empty().append(original).append(invalidation)
        snapshot = StateCompiler().compile(history, version_tuple())
        self.assertEqual({}, snapshot.state_by_subject())
        self.assertEqual({"lifecycle": "PENDING"}, original.payload()["state_projection"])

    def test_conflicting_active_assertions_fail_closed(self):
        history = FactHistory.empty()
        history = history.append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        history = history.append(state_fact("ORDER:001", {"lifecycle": "ACTIVE"}))
        with self.assertRaises(StateCompilationError):
            StateCompiler().compile(history, version_tuple())

    def test_malformed_projection_fails_closed(self):
        malformed = Fact.create(
            fact_type="assertion",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:00:00Z",
            payload={"state_projection": []},
            provenance=provenance(),
        )
        with self.assertRaises(StateCompilationError):
            StateCompiler().compile(FactHistory.empty().append(malformed), version_tuple())

    def test_decision_is_non_interfering_and_is_not_state_projection(self):
        candidate = CandidateProposal.create(
            subject_id="ORDER:001",
            requested_transition="ORDER:001 -> ACTIVE",
            evidence_refs=("EVIDENCE:K1:CANDIDATE",),
        )
        denial = build_decision_fact(
            candidate=candidate,
            decision="DENY",
            reason="authority_pending",
            occurred_at="2026-09-25T00:02:00Z",
            provenance=provenance(),
            state_ref="STATE:K1:CANDIDATE",
            constraint_refs=("CONSTRAINT:AUTHORITY",),
            policy_ref="POLICY:K1:CANDIDATE_ONLY",
            authority_ref="AUTHORITY:PENDING",
            version_tuple=version_tuple(),
        )
        snapshot = StateCompiler().compile(FactHistory.empty().append(denial), version_tuple())
        self.assertEqual({}, snapshot.state_by_subject())

    def test_decision_carrying_state_projection_is_rejected(self):
        decision = Fact.create(
            fact_type="decision",
            subject_id="ORDER:001",
            occurred_at="2026-09-25T00:02:00Z",
            payload={"decision": "DENY", "state_projection": {"lifecycle": "ACTIVE"}},
            provenance=provenance(),
        )
        with self.assertRaises(StateCompilationError):
            StateCompiler().compile(FactHistory.empty().append(decision), version_tuple())

    def test_non_contributing_fact_type_carrying_state_projection_is_rejected(self):
        proposed_transition = state_fact(
            "ORDER:001",
            {"lifecycle": "ACTIVE"},
            fact_type="transition_proposed",
        )
        with self.assertRaises(StateCompilationError):
            StateCompiler().compile(FactHistory.empty().append(proposed_transition), version_tuple())

    def test_snapshot_is_immutable_value_and_returns_copy(self):
        history = FactHistory.empty().append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        snapshot = StateCompiler().compile(history, version_tuple())
        copied = snapshot.state_by_subject()
        copied["ORDER:001"]["lifecycle"] = "ACTIVE"
        self.assertEqual({"ORDER:001": {"lifecycle": "PENDING"}}, snapshot.state_by_subject())
        snapshot.verify()

    def test_cache_recompiles_history_and_has_no_public_state_writer(self):
        history = FactHistory.empty().append(state_fact("ORDER:001", {"lifecycle": "PENDING"}))
        cache = SnapshotCache(StateCompiler())
        snapshot = cache.derive(history, version_tuple())
        self.assertEqual(snapshot.snapshot_id, cache.lookup(history_id=history.history_id, version_tuple=version_tuple()).snapshot_id)
        self.assertFalse(hasattr(cache, "put"))
        self.assertFalse(hasattr(cache, "write_state"))
        self.assertFalse(hasattr(cache, "update"))
        self.assertFalse(hasattr(cache, "delete"))


if __name__ == "__main__":
    unittest.main()
