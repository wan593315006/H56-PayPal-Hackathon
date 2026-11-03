# Version and Migration Recommendation V1

## Profile change rule

```text
Runtime observation or Agent proposal
→ Ontology Change Candidate
→ offline compatibility audit
→ Controller review
→ new immutable profile version
```

No Runtime execution, Candidate, State, observation or legacy project may add
a type, relation, dimension or extension to the active profile directly.

## Required compatibility outcomes

| Outcome | Meaning |
| --- | --- |
| `COMPATIBLE` | Existing source-bound object remains interpretable without changed meaning. |
| `MIGRATION_REQUIRED` | A declared, reviewable mapping is required before use under the new profile. |
| `UNSUPPORTED` | The old object cannot enter the new profile. |
| `AMBIGUOUS` | More than one interpretation is possible; fail closed pending clarification. |

## Non-negotiable rules

1. Every projection must carry `ontology_profile_id`, profile version and
   content hash.
2. A new profile never silently reinterprets an old object or State instance.
3. Profile compatibility does not establish P11/P12, live-session continuation
   or an authoritative State migration.
4. A migration payload may include a new profile only through its own coverage
   registration and future recovery verification.
