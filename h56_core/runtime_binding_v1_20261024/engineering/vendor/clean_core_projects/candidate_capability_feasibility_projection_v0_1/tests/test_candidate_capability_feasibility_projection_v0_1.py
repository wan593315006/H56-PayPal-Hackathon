from dataclasses import replace
import hashlib
from pathlib import Path
import sys

import pytest

from candidate_capability_feasibility_projection import (
    CapabilityAvailabilityAssertion,
    CapabilityCatalogReference,
    CandidateCapabilityFeasibleSet,
    CapabilityFeasibilityError,
    CandidateCapabilityFeasibilityEvaluator,
    FeasibilityContext,
)
from candidate_capability_feasibility_projection.contracts import canonical_sha256


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from verify_c1_canonical_capability_contract_binding import (  # noqa: E402
    C1BindingError,
    load_binding,
    verify_c1_binding,
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reference(**overrides):
    value = {
        "catalog_id": "CAPABILITY_CATALOG:CANDIDATE:V1",
        "catalog_version": "1.0.0",
        "catalog_hash": digest("c1-catalog"),
        "contract_project_id": "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1",
        "contract_commit": "b01fa57f22c108e60ab26b1b285417d50f62b10c",
        "contract_manifest_sha256": "9ed5f996152a4de096206a54f09e9d6b8b2866a5ef2593cd1a9c619ea2e0c723",
        "capability_id": "CAP:STRUCTURED_AUDIT:CAPTURE:V1",
        "definition_hash": digest("c1-definition"),
    }
    value.update(overrides)
    value["reference_hash"] = canonical_sha256(value)
    return CapabilityCatalogReference.from_mapping(value)


def assertion(**overrides):
    value = {
        "capability_id": "CAP:STRUCTURED_AUDIT:CAPTURE:V1",
        "definition_hash": digest("c1-definition"),
        "availability_state": "DECLARED_AVAILABLE",
        "allowed_task_kinds": ["TASK:STRUCTURED_AUDIT:V1"],
        "allowed_state_patterns": ["STATE:INPUT_READY:V1"],
        "allowed_method_ids": ["METHOD:STRUCTURED_AUDIT:V1"],
        "minimum_budget_units": 3,
        "required_evidence_state": "SUFFICIENT",
    }
    value.update(overrides)
    value["assertion_hash"] = canonical_sha256(value)
    return CapabilityAvailabilityAssertion.from_mapping(value)


def context(**overrides):
    value = {
        "task_kind": "TASK:STRUCTURED_AUDIT:V1",
        "task_snapshot_hash": digest("task"),
        "state_pattern": "STATE:INPUT_READY:V1",
        "state_snapshot_hash": digest("state"),
        "method_id": "METHOD:STRUCTURED_AUDIT:V1",
        "method_hash": digest("method"),
        "policy_state": "DECLARED_ALLOWED",
        "policy_snapshot_hash": digest("policy"),
        "authority_state": "DECLARED_SUFFICIENT",
        "authority_snapshot_hash": digest("authority"),
        "budget_available_units": 5,
        "budget_snapshot_hash": digest("budget"),
        "evidence_state": "SUFFICIENT",
        "evidence_snapshot_hash": digest("evidence"),
    }
    value.update(overrides)
    value["context_hash"] = canonical_sha256(value)
    return FeasibilityContext.from_mapping(value)


def project(**context_overrides):
    return CandidateCapabilityFeasibilityEvaluator().project(
        catalog=reference(), assertion=assertion(), context=context(**context_overrides)
    )


def test_matching_declarations_are_feasible_only_for_candidate_planning():
    result = project()
    assert result.decision == "FEASIBLE"
    assert result.reason_codes == ("DECLARED_CANDIDATE_FEASIBILITY_MATCH",)
    assert result.candidate_planning_only
    assert not result.authority_granted
    assert not result.execution_permitted
    result.verify()


def test_declared_unavailable_capability_is_infeasible():
    result = CandidateCapabilityFeasibilityEvaluator().project(
        catalog=reference(), assertion=assertion(availability_state="DECLARED_UNAVAILABLE"), context=context()
    )
    assert result.decision == "INFEASIBLE"
    assert result.reason_codes == ("DECLARED_CAPABILITY_UNAVAILABLE",)


def test_unknown_availability_defers_without_resolving_any_tool():
    result = CandidateCapabilityFeasibilityEvaluator().project(
        catalog=reference(), assertion=assertion(availability_state="DECLARED_UNKNOWN"), context=context()
    )
    assert result.decision == "DEFER"
    assert result.reason_codes == ("CAPABILITY_AVAILABILITY_NOT_EVIDENCED",)


def test_task_state_and_method_mismatches_are_infeasible():
    assert project(task_kind="TASK:OTHER:V1").reason_codes == ("TASK_KIND_OUT_OF_DECLARED_SCOPE",)
    assert project(state_pattern="STATE:OTHER:V1").reason_codes == ("STATE_PATTERN_OUT_OF_DECLARED_SCOPE",)
    assert project(method_id="METHOD:OTHER:V1").reason_codes == ("METHOD_OUT_OF_DECLARED_SCOPE",)


def test_policy_denial_and_unknown_context_do_not_become_feasible():
    assert project(policy_state="DECLARED_DENIED").reason_codes == ("DECLARED_POLICY_DENIED",)
    result = project(policy_state="DECLARED_UNKNOWN")
    assert result.decision == "DEFER"
    assert result.reason_codes == ("POLICY_CONTEXT_NOT_EVIDENCED",)


def test_non_sufficient_authority_context_defers_without_creating_authority():
    result = project(authority_state="DECLARED_INSUFFICIENT")
    assert result.decision == "DEFER"
    assert result.reason_codes == ("AUTHORITY_CONTEXT_NOT_SUFFICIENT",)
    assert not result.authority_granted


def test_budget_and_evidence_gaps_do_not_become_feasible():
    assert project(budget_available_units=2).reason_codes == ("DECLARED_BUDGET_INSUFFICIENT",)
    result = project(evidence_state="UNKNOWN")
    assert result.decision == "NEED_MORE_EVIDENCE"
    assert result.reason_codes == ("EVIDENCE_REQUIREMENT_NOT_SATISFIED",)


def test_catalog_definition_binding_mismatch_is_infeasible():
    bad = assertion(definition_hash=digest("other-definition"))
    result = CandidateCapabilityFeasibilityEvaluator().project(catalog=reference(), assertion=bad, context=context())
    assert result.decision == "INFEASIBLE"
    assert result.reason_codes == ("C1_DEFINITION_BINDING_MISMATCH",)


def test_hidden_context_mutation_reusing_old_hash_fails_closed():
    value = {
        "task_kind": "TASK:STRUCTURED_AUDIT:V1", "task_snapshot_hash": digest("task"),
        "state_pattern": "STATE:INPUT_READY:V1", "state_snapshot_hash": digest("state"),
        "method_id": "METHOD:STRUCTURED_AUDIT:V1", "method_hash": digest("method"),
        "policy_state": "DECLARED_ALLOWED", "policy_snapshot_hash": digest("policy"),
        "authority_state": "DECLARED_SUFFICIENT", "authority_snapshot_hash": digest("authority"),
        "budget_available_units": 5, "budget_snapshot_hash": digest("budget"),
        "evidence_state": "SUFFICIENT", "evidence_snapshot_hash": digest("evidence"),
    }
    value["context_hash"] = canonical_sha256(value)
    value["budget_available_units"] = 500
    with pytest.raises(CapabilityFeasibilityError, match="FEASIBILITY_CONTEXT_HASH_MISMATCH"):
        FeasibilityContext.from_mapping(value)


def test_tampered_projection_is_detected_and_cannot_gain_operational_rights():
    result = project()
    with pytest.raises(CapabilityFeasibilityError, match="FEASIBILITY_PROJECTION_IDENTITY_DRIFT"):
        replace(result, authority_granted=True).verify()


def test_same_context_projections_form_a_trace_preserving_candidate_feasible_set():
    second_catalog = reference(
        capability_id="CAP:STRUCTURED_AUDIT:EVALUATE:V1",
        definition_hash=digest("c1-definition-evaluate"),
    )
    second_assertion = assertion(
        capability_id="CAP:STRUCTURED_AUDIT:EVALUATE:V1",
        definition_hash=digest("c1-definition-evaluate"),
        availability_state="DECLARED_UNAVAILABLE",
    )
    evaluator = CandidateCapabilityFeasibilityEvaluator()
    result = evaluator.project_set(
        (
            (reference(), assertion(), context()),
            (second_catalog, second_assertion, context()),
        )
    )
    assert result.feasible_capability_ids == ("CAP:STRUCTURED_AUDIT:CAPTURE:V1",)
    assert len(result.projection_hashes) == 2
    assert result.candidate_planning_only
    assert not result.authority_granted and not result.execution_permitted
    result.verify()


def test_feasible_set_rejects_unsorted_or_cross_context_projections():
    first = project()
    later = CandidateCapabilityFeasibilityEvaluator().project(
        catalog=reference(capability_id="CAP:STRUCTURED_AUDIT:ZETA:V1"),
        assertion=assertion(capability_id="CAP:STRUCTURED_AUDIT:ZETA:V1"),
        context=context(),
    )
    with pytest.raises(CapabilityFeasibilityError, match="PROJECTIONS_NOT_SORTED"):
        CandidateCapabilityFeasibleSet.create((later, first))
    changed_context = context(budget_available_units=6)
    changed = CandidateCapabilityFeasibilityEvaluator().project(
        catalog=reference(capability_id="CAP:STRUCTURED_AUDIT:ZETA:V1"),
        assertion=assertion(capability_id="CAP:STRUCTURED_AUDIT:ZETA:V1"),
        context=changed_context,
    )
    with pytest.raises(CapabilityFeasibilityError, match="CONTEXT_MISMATCH"):
        CandidateCapabilityFeasibleSet.create((first, changed))


def test_c1_contract_binding_is_recomputed_before_c2_regression():
    result = verify_c1_binding()
    assert result["result"] == "PASS_C1_CONTRACT_BINDING"
    assert result["managed_file_count"] == 17


def test_c1_contract_binding_drift_fails_closed():
    binding = dict(load_binding())
    binding["project_manifest_sha256"] = digest("forged-c1-manifest")
    with pytest.raises(C1BindingError, match="C1_PROJECT_MANIFEST_HASH_DRIFT"):
        verify_c1_binding(binding)
