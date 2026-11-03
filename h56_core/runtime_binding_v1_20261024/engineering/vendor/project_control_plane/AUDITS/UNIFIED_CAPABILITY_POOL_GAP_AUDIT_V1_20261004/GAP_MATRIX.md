# Unified Capability Pool Gap Matrix V1

## Verdict

```ini
UNIFIED_CAPABILITY_POOL = PARTIAL_CANDIDATE_FOUNDATION
CAPABILITY_DEFINITION = PARTIAL_SOURCE_AND_EXECUTED_EVIDENCE
CAPABILITY_AVAILABILITY = MISSING_GENERIC_CONTRACT
CAPABILITY_FEASIBLE_SET = MISSING
MULTI_AGENT_RUNTIME_ORGANIZATION = NOT_ESTABLISHED
MULTI_AGENT_AUTONOMOUS_COORDINATION = FORBIDDEN
```

## Capability findings

| Capability concern | Status | Evidence | Limit / required repair |
| --- | --- | --- | --- |
| Fixed capability identity and version | PARTIAL | V0.4 Registry and V0.5 `CapabilityDefinition`, dual-Python tests | IDs are local fixed catalogs; no cross-project canonical contract. |
| Definition integrity | EXISTING candidate | V0.4/V0.5 definition hashes and manifest/source receipts | A registry entry is not a real executable availability assertion. |
| Typed input/output | EXISTING candidate | V0.4 Contract; V0.5 input/output kinds | Need universal schema compatibility rules in C1. |
| Preconditions, Scope and failure boundary | PARTIAL | V0.4 static contract; V0.5 chain phase | Need common language for preconditions, effects, and forbidden scope. |
| Risk and resource requirement | PARTIAL | V0.14 has bounded `resource_budget`; V0.4 scope limits | No cross-capability risk/resource semantics. |
| Observation requirement | PARTIAL | V0.4 observer contract; V0.5 observation/evidence stages | No generic evidence-quality or freshness relation. |
| Source/provenance | PARTIAL | Frozen source identities and Data Source Trust descriptors | No live source authenticity; no external Trust root. |
| `CapabilityAvailability` | MISSING | No current source computes present feasibility from State/Policy/Authority/Budget/Evidence | C2 must introduce a candidate-only projection. |
| `CapabilityFeasibleSet` | MISSING | No source-bound set exists | C2 must be deterministic and non-authoritative. |
| Tool/execution authority | CONFLICT if inferred | Existing projects expressly forbid execution and dynamic plugins | Must remain outside Capability Pool. |

## Separation rules for C1 and C2

```text
Definition:
  identity + contract + scope + risk + evidence requirements

Availability:
  Definition + Task + State + Method + Policy + Authority + Budget + Evidence
  -> FEASIBLE | INFEASIBLE | DEFER | NEED_MORE_EVIDENCE
```

`FEASIBLE` can only enter a candidate planning set.  It is never an Authority,
an action permission, a Commit, or execution permission.

## C1/C2 entry gate

`C1_CANONICAL_CAPABILITY_CONTRACT_V0_1` may start as a separate candidate
project.  It must consume only public, source-bound declaration-shaped inputs.
`C2_CAPABILITY_FEASIBILITY_PROJECTION_V0_1` must wait until C1 is frozen and
its Definition input integrity is proved.
