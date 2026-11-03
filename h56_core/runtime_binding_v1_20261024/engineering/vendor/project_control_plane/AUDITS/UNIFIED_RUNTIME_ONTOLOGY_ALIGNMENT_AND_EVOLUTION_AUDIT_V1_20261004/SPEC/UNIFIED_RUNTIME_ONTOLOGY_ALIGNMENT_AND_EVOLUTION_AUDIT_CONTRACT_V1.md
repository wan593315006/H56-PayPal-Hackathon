# Unified Runtime Ontology Alignment and Evolution Audit Contract V1

## 1. Task and authority

Task type: `read_only_analysis` plus `mainline_update` of this audit package.
The Controller authorized a study and evidence package, not an Ontology
Runtime, a profile replacement or a Kernel change.

## 2. Semantic boundary

The audit distinguishes three orthogonal planes:

```text
Ontology = type-level semantic vocabulary and allowed relation meanings
State    = concrete instances and declared current conditions
Kernel   = feasibility, governance and legal transition adjudication
```

An Ontology relation type being valid never proves an instance relation is
currently true or legally established.  Only the applicable Kernel contract
may make that decision.

## 3. Required audit outputs

1. candidate Core terms and recommended canonical semantic IDs;
2. versioned Extension Profile candidates;
3. relation vocabulary with source/target, direction, cardinality, temporal,
   version and authority-scope status;
4. read-only mapping rules from local project terms to common semantics;
5. unknown-extension and profile-change governance;
6. Profile-version compatibility/migration interpretation; and
7. a static authority/effect boundary.

## 4. Evidence rule

`DOCUMENT < SOURCE < REACHABLE < EXECUTED` remains mandatory.  A local class
name, a description or a relation-like hash alone is not evidence of a
universal semantic contract.  Every `EXISTING` result is candidate-scoped and
does not grant authoritative State, Authority, Runtime, execution or formal
MLM status.

## 5. Status vocabulary

Only `EXISTING`, `PARTIAL`, `MISSING`, `CONFLICT` and `PROPOSED` are used.
`PROPOSED` means a useful V1.1 recommendation without enough admissible
evidence to freeze it as current shared semantics.

## 6. Non-negotiable prohibitions

```ini
LEGACY_DIRECT_IMPORT_OR_BRIDGE = FORBIDDEN
ONTOLOGY_STATE_OR_HISTORY_WRITE = FORBIDDEN
ONTOLOGY_AUTHORITY_OR_COMMIT_ISSUE = FORBIDDEN
ONTOLOGY_POLICY_OR_EXECUTION = FORBIDDEN
RUNTIME_AUTOMATIC_PROFILE_MUTATION = FORBIDDEN
UNKNOWN_OBJECT_RELATION_OR_DIMENSION = FAIL_CLOSED
```

## 7. Completion condition

Completion produces only an evidence-backed V1.1 recommendation.  A separate
Controller decision is required before freezing a profile, adding a mapping
adapter, changing a migration payload or implementing any ontology service.
