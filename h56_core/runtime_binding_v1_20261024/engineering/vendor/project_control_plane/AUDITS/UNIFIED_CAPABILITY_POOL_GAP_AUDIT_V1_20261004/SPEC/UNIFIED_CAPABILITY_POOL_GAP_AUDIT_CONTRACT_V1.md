# C0 — Unified Capability Pool Gap Audit Contract V1

## Task type and authority

`read_only_analysis` followed by `mainline_update` for its own audit record.
The Controller authorized this audit and the construction sequence
`C0 → C1 → C2 → A0 → A1`; this C0 artifact does not authorize any later
implementation by itself.

## Evidence admissibility

```text
DOCUMENT < SOURCE < REACHABLE < EXECUTED
```

Historical prerequisite slices prove only design intent.  A source file proves
implementation existence.  A reachable call path and executed test/replay are
required before a surface is labelled `EXISTING`.

## Audit questions

For every candidate Capability surface, determine whether evidence supports:

1. stable identity, version, and integrity;
2. input/output contract and Preconditions;
3. scope and forbidden side effects;
4. risk, resource/budget and failure boundary;
5. observation/evidence requirement;
6. current availability separately from Definition; and
7. whether the result can safely feed a future Agent-organization planner.

## Required outputs

- `CAPABILITY_SURFACE_MANIFEST.json`
- `GAP_MATRIX.md`
- `AGENT_ORGANIZATION_PRECHECK.md`
- source and replay evidence manifests;
- an integrity manifest; and
- a C0 task card and control-plane registration.

## Explicit exclusions

No Canonical Capability Contract, CapabilityFeasibleSet, Agent Organization
engine, Agent creation, live scheduling, tool adapter, capability execution,
Authority, Commit, State/History write, or runtime bridge is produced.

## Pass / fail

PASS requires each C0 conclusion to name evidence strength and scope, preserve
all current candidate-only boundaries, and identify the exact C1/C2/A0/A1
gates.  A module/function name alone is insufficient evidence.
