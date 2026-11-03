# Unified Runtime Ontology Profile V1.1 Requirement

## Objective

Freeze a deterministic candidate semantic profile that preserves the hard
separation:

```text
Ontology = type vocabulary, relation meaning and profile version rules
State    = an instance-level declared/derived condition
Kernel   = the only legal-transition and governance adjudicator
```

## Required semantics

- ten Core terms: Task, State, Candidate, Capability, Method, Observation,
  Evidence, Policy, Authority and Session;
- versioned Data, Method, Trust and Resource extension profiles;
- directed relations with explicit source/target, cardinality, temporal form,
  candidate scope, evidence requirement and forbidden inference;
- fixed context dimensions; and
- content hash, strict exact-key parsing, unknown-item rejection and declared
  profile-compatibility outcomes.

## Hard exclusions

The profile must not read or write State/History/Runtime, resolve a live
object, issue Authority/Commit, execute Policy, call an Adapter or external
tool, import/call legacy Five-Body, contact a network, or mutate any profile.

## Result

The only permitted result is a locally constructed, content-bound
`RuntimeOntologyProfile` or `ReadOnlyOntologyDescriptor`.  Neither is an
authority, a registry entry, a current State, an execution permission or a
Fact.
