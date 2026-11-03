# Unified Runtime Ontology Alignment and Evolution Gap Matrix V1

## Verdict

```ini
UNIFIED_RUNTIME_ONTOLOGY_CANDIDATE_SEED = EXISTING
CURRENT_PROFILE = CANDIDATE_RUNTIME_ONTOLOGY_PROFILE_V1
CORE_VOCABULARY = EXISTING_CANDIDATE_ONLY
CANONICAL_SEMANTIC_ID_NAMESPACE = PROPOSED
EXTENSION_PROFILE_GOVERNANCE = PARTIAL
RELATION_TYPE_PAIRS = EXISTING_CANDIDATE_ONLY
RELATION_CARDINALITY_TEMPORAL_VERSION_SEMANTICS = PARTIAL
ONTOLOGY_PROFILE_COMPATIBILITY_AND_MIGRATION_POLICY = MISSING
ONTOLOGY_RUNTIME_OR_KERNEL_OWNERSHIP = CONFLICT
LEGACY_ONTOLOGY_DIRECT_BRIDGE = CONFLICT
```

## A. Core candidate vocabulary

| Recommended semantic ID | Current profile term | Status | Evidence and limit |
| --- | --- | --- | --- |
| `uro:Task` | `TASK` | EXISTING | V0.14 profile/test; candidate Task contracts map only by future read-only mapping. |
| `uro:State` | `STATE` | PARTIAL | Candidate State shape exists; K1 derived State and experimental State have no normalized instance relationship. |
| `uro:Candidate` | `CANDIDATE` | EXISTING | V0.14 profile plus K2/V0.5 candidate contracts; no authority follows. |
| `uro:Capability` | `CAPABILITY` | EXISTING | V0.14 contract/version fields and V0.5 capability catalog material. |
| `uro:Method` | `METHOD` | EXISTING | Source/version/applicability fields are profile-bound; no formal Method promotion. |
| `uro:Observation` | `OBSERVATION` | EXISTING | Candidate observation receipts only; not an authoritative Fact. |
| `uro:Evidence` | `EVIDENCE` | EXISTING | Hash/quality evidence shape is established; universal quality lattice is absent. |
| `uro:Policy` | `POLICY` | EXISTING | Policy hash/version is represented; cross-package policy interpretation is partial. |
| `uro:Authority` | `AUTHORITY` | PARTIAL | Candidate descriptor exists; real Authority/Trust remains unprovisioned. |
| `uro:Session` | `SESSION` | EXISTING | Candidate journal/lifecycle exists; no cross-machine continuation semantics. |

The `uro:*` identifiers are recommendations, not a new registry or an active
resolver.  Their purpose is to map heterogeneous names without changing their
source projects.

## B. Extension candidates

| Profile | Candidate terms | Status | Boundary |
| --- | --- | --- | --- |
| `uro-data:*` | DataRequirement, DataSubmission, DataReadinessReceipt, SourceTrustClaim, SourceTrustAssessment, DataGapCandidate | EXISTING candidate material | No global data ontology, data read, source authenticity or K2 authority. |
| `uro-method:*` | EvidenceAtom, Episode, Pattern, MethodSkeleton, DomainBinding, FormalOperator, MethodFragment, CandidateEvidenceReplay | EXISTING candidate material | No formal MethodPack promotion, M2 composition or formal MLM write. |
| `uro-trust:*` | SourceAuthorizationScope, Attestation, RevocationView, ExternalTrustVerification | PARTIAL | Contract is structural and `DEFER`-only; no external trust implementation. |
| `uro-resource:*` | ResourceBudget | PARTIAL | A bounded Task/dispatch value exists, but not a generic cross-capability resource model. |

An extension never becomes Core merely because it is useful.  It must have a
stable cross-chain meaning, a frozen profile, compatibility evidence and a
Controller-approved profile version.

## C. Relation and lifecycle findings

V0.14 proves ten source/target relation pairs and rejects unknown pairs.  It
does not yet define cardinality, temporal duration, version compatibility or
inheritance for every pair.  Those semantics are `PARTIAL`, not silently
assumed.  Proposed extension relations likewise remain `PROPOSED`.

## D. Required Controller decision after this audit

The only recommended decision is whether to freeze a **read-only**
`UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1` candidate.  It must not replace V0.14,
change State/K0/K1/Kernel behavior, create a live ontology registry, or alter
the frozen migration payload without its own scope and evidence.
