# Unified Capability Pool Gap Audit V1

## Purpose

This is a read-only audit of the candidate Capability surfaces already present
in Five-Body.  It separates two questions which must never be conflated:

```text
Capability Definition = what a capability is.
Capability Availability = whether that capability is presently feasible.
```

It neither creates a live Capability Pool nor treats a registered capability
as an Authority, a Commit, or an executable tool.

## Baseline and scope

- Audit baseline commit: `0a44ae5125e366a1de3d3070142992d884e44af1`
- Audit baseline tree: resolved during closeout from the repository.
- Evidence is limited to source-bound candidate projects, current control-plane
  records, and the historical prerequisite slice as a `DOCUMENT`-strength
  design reference.

## Result

The system has a **partial candidate foundation**:

- V0.4 proves a registered-capability contract for three fixed task profiles.
- V0.5 proves seven fixed definitions across three heterogeneous capability
  chains, source-bound Method references, observation, replay, and explicit
  no-multi-Agent coordination.
- Data-readiness and candidate Ontology projects provide bounded Capability
  inputs and vocabulary, but not a universal availability model.

It lacks a source-bound, generic `CapabilityAvailability` contract and a
`CapabilityFeasibleSet` computed from Task, State, Method, Policy, Authority,
Budget, and Evidence.  Therefore no multi-Agent runtime organization may be
constructed from existing materials.

## Hard boundary

```ini
CAPABILITY_DEFINED ≠ AVAILABLE_NOW
FEASIBLE ≠ AUTHORIZED ≠ EXECUTABLE
CAPABILITY_POOL ≠ TOOL_REGISTRY
AGENT_ORGANIZATION ≠ AUTHORITY_SOURCE
```

No old-runtime import/call, dynamic plugin, external data read, network, MCP,
Provider, bus, Pipeline, K0/K1/Runtime/formal-MLM write, Authority/Commit
creation, Agent creation, or execution occurs in this audit.
