# Candidate Canonical Capability Contract V0.1 — Requirement

## Objective

Create a minimal, deterministic, source-bound candidate contract that defines
the identity and declared semantics of a Capability without confusing that
definition with present feasibility or execution rights.

```text
Capability Definition = what a Capability is
Capability Availability = whether it is feasible now

CAPABILITY_DEFINED != AVAILABLE_NOW
FEASIBLE != AUTHORIZED != EXECUTABLE
```

## Accepted declaration shape

Each `CapabilityDefinition` must bind:

- `capability_id`, `version`, and deterministic `definition_hash`;
- typed input and output contract descriptors;
- precondition, scope, resource, failure-boundary and observation descriptors;
- declared risk class;
- source ID, version and content hash;
- one known extension profile.

The hash covers the full declaration body.  A changed hidden value with a
reused old hash must fail closed.

`CanonicalCapabilityCatalog` must bind a unique set of definitions and its
own deterministic catalog hash.  It is immutable after construction and is
not a live registry, resolver or plugin loader.

## Explicit exclusions

This project must not expose or infer:

- present availability, feasible sets, Authority, ATP, Commit or execution;
- a tool adapter, Agent, external data reader, dynamic plugin or legacy bridge;
- a write to History, State, Runtime or formal MLM;
- network, MCP, Provider, bus, Pipeline or production side effects.

## Candidate status

All source/provenance fields are content-bound declarations.  They do not
prove real-world source authenticity, a Trust Root, or an independent issuer.

## Acceptance evidence

1. deterministic identity and catalog replay;
2. duplicate IDs, unknown fields/profiles and reused hashes fail closed;
3. a definition cannot carry availability, authority or execution fields;
4. static boundary audit passes under Python 3.9 and 3.13;
5. the frozen C0 audit manifest and all of its declared materials are
   recomputed before C1 regression;
6. project-manifest integrity is recomputed and verified;
7. structured candidate semantic review has zero issues.

## Stop

After C1 closeout, stop.  C2 can only begin under separate Controller scope
and may consume the frozen public C1 contract; it may not infer execution
permission from a definition.
