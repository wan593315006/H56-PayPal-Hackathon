"""Deterministic candidate feasibility decision rules."""

from __future__ import annotations

from typing import Tuple

from .contracts import CandidateCapabilityFeasibleSet, CapabilityAvailabilityAssertion, CapabilityCatalogReference, FeasibilityContext, FeasibilityProjection


class CandidateCapabilityFeasibilityEvaluator:
    """Pure evaluator: it never resolves, authorises or executes a Capability."""

    def project(self, *, catalog: CapabilityCatalogReference, assertion: CapabilityAvailabilityAssertion, context: FeasibilityContext) -> FeasibilityProjection:
        catalog.verify()
        assertion.verify()
        context.verify()
        if catalog.capability_id != assertion.capability_id or catalog.definition_hash != assertion.definition_hash:
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("C1_DEFINITION_BINDING_MISMATCH",))
        if assertion.availability_state == "DECLARED_UNAVAILABLE":
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("DECLARED_CAPABILITY_UNAVAILABLE",))
        if assertion.availability_state == "DECLARED_UNKNOWN":
            return FeasibilityProjection.create(catalog, assertion, context, "DEFER", ("CAPABILITY_AVAILABILITY_NOT_EVIDENCED",))
        if context.task_kind not in assertion.allowed_task_kinds:
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("TASK_KIND_OUT_OF_DECLARED_SCOPE",))
        if context.state_pattern not in assertion.allowed_state_patterns:
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("STATE_PATTERN_OUT_OF_DECLARED_SCOPE",))
        if context.method_id not in assertion.allowed_method_ids:
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("METHOD_OUT_OF_DECLARED_SCOPE",))
        if context.policy_state == "DECLARED_DENIED":
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("DECLARED_POLICY_DENIED",))
        if context.policy_state == "DECLARED_UNKNOWN":
            return FeasibilityProjection.create(catalog, assertion, context, "DEFER", ("POLICY_CONTEXT_NOT_EVIDENCED",))
        if context.authority_state != "DECLARED_SUFFICIENT":
            return FeasibilityProjection.create(catalog, assertion, context, "DEFER", ("AUTHORITY_CONTEXT_NOT_SUFFICIENT",))
        if context.budget_available_units < assertion.minimum_budget_units:
            return FeasibilityProjection.create(catalog, assertion, context, "INFEASIBLE", ("DECLARED_BUDGET_INSUFFICIENT",))
        if context.evidence_state != "SUFFICIENT" or assertion.required_evidence_state != "SUFFICIENT":
            return FeasibilityProjection.create(catalog, assertion, context, "NEED_MORE_EVIDENCE", ("EVIDENCE_REQUIREMENT_NOT_SATISFIED",))
        return FeasibilityProjection.create(catalog, assertion, context, "FEASIBLE", ("DECLARED_CANDIDATE_FEASIBILITY_MATCH",))

    def project_set(self, entries: Tuple[Tuple[CapabilityCatalogReference, CapabilityAvailabilityAssertion, FeasibilityContext], ...]) -> CandidateCapabilityFeasibleSet:
        projections = tuple(
            self.project(catalog=catalog, assertion=assertion, context=context)
            for catalog, assertion, context in entries
        )
        return CandidateCapabilityFeasibleSet.create(projections)
