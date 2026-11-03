# Relation Vocabulary Recommendation V1

## Current candidate relation pairs

The following pairs are current V0.14 candidate-profile evidence, not a claim
that every relationship instance is legally true:

| V0.14 source relation contract | Candidate relation ID | Source → target | Current semantic status |
| --- | --- | --- | --- |
| `SESSION_CONTAINS_TASK` | `uro:sessionContainsTask` | Session → Task | EXISTING pair; cardinality/time semantics PARTIAL. |
| `TASK_HAS_STATE` | `uro:taskHasState` | Task → State | EXISTING pair; no automatic State writer. |
| `TASK_REQUESTS_CANDIDATE` | `uro:taskRequestsCandidate` | Task → Candidate | EXISTING pair; request is not authorization. |
| `CANDIDATE_USES_CAPABILITY` | `uro:candidateUsesCapability` | Candidate → Capability | EXISTING pair; use is not execution. |
| `CANDIDATE_SELECTS_METHOD` | `uro:candidateSelectsMethod` | Candidate → Method | EXISTING pair; selection is not promotion. |
| `CANDIDATE_GOVERNED_BY_POLICY` | `uro:candidateGovernedByPolicy` | Candidate → Policy | EXISTING pair; profile does not execute Policy. |
| `CANDIDATE_BOUND_BY_AUTHORITY` | `uro:candidateBoundByAuthority` | Candidate → Authority | EXISTING candidate descriptor; real Authority is PARTIAL/unprovisioned. |
| `CANDIDATE_PRODUCES_OBSERVATION` | `uro:candidateProducesObservation` | Candidate → Observation | EXISTING candidate pair; does not admit Fact. |
| `OBSERVATION_YIELDS_EVIDENCE` | `uro:observationYieldsEvidence` | Observation → Evidence | EXISTING candidate pair; evidence quality remains local. |
| `EVIDENCE_SUPPORTS_METHOD` | `uro:evidenceSupportsMethod` | Evidence → Method | EXISTING candidate pair; support is not formal promotion. |

## Required V1.1 semantics per relation

Before a relation is frozen in V1.1, it needs explicit values for:

```text
source_type, target_type, direction, cardinality, temporal_semantics,
profile_version_compatibility, candidate_or_authoritative_scope,
evidence_requirement, and forbidden_inference.
```

## Proposed extension relations

The following are useful but remain `PROPOSED`: `uro-data:TaskRequiresData`,
`uro-data:SubmissionSatisfiesRequirement`, `uro-data:DescriptorDescribesSubmission`,
`uro-method:EpisodeContainsEvidence`, `uro-method:PatternAbstractsEpisode`,
`uro-method:SkeletonAbstractsPattern`, and `uro-method:BindingBindsSkeleton`.

They cannot be implemented as live relations or used by the Kernel until their
source/target semantics, lifecycle and evidence rules are independently frozen.
