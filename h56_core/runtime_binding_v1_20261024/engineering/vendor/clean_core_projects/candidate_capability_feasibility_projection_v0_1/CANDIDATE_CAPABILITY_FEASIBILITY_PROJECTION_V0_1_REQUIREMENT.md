# Candidate Capability Feasibility Projection V0.1 — Requirement

## Objective

Compute a deterministic candidate feasibility result for a declared C1
Capability Definition under a declared bounded context:

```text
Task + State + Method + Policy + Authority + Budget + Evidence + Capability Pool
-> FEASIBLE | INFEASIBLE | DEFER | NEED_MORE_EVIDENCE

Ordered projections for the same frozen context
-> Candidate CapabilityFeasibleSet
```

## Contract rules

- C1 Definition and present feasibility remain distinct.
- C1 input is a public catalog reference and declared definition hash; no C1
  package import, legacy bridge, registry call or tool lookup is permitted.
- Every input claim is self-hash-bound. Mutating a hidden value while retaining
  an old hash fails closed.
- `FEASIBLE` means only that candidate declarations match the frozen rules. It
  is neither Authority, action permission, ATP, Commit nor execution.
- `CandidateCapabilityFeasibleSet` includes all verified projections in one
  frozen context, requires unique sorted Capability IDs, and exposes only the
  candidate-feasible subset. It cannot discard non-feasible decision traces.
- `DECLARED_UNKNOWN` availability or governance context returns `DEFER`.
- missing or insufficient evidence returns `NEED_MORE_EVIDENCE`.
- mismatched task, state, method, policy, budget or declared unavailability
  returns `INFEASIBLE` with source-bound reasons.

## Explicit exclusions

No external Capability lookup, dynamic plugin, Agent creation or coordination,
network, MCP, Provider, bus, Pipeline, source/data read, History/State/Runtime
or formal-MLM write, Authority/Commit creation, tool call or real execution.

## Acceptance evidence

1. deterministic candidate projection/set and tamper detection;
2. each decision class is covered by a negative or positive test;
3. C1 project manifest and all its declared files are rechecked before C2
   regression;
4. dual-Python static-boundary, manifest and semantic-review checks pass;
5. C2 is registered as required in the next candidate cold-start payload but
   remains absent from immutable r11, causing coverage fail-closed.

## Stop

Stop after C2. A0 may audit Agent Organization only after C2 is frozen. C2
does not authorize Agent creation, coordination, Authority or execution.
