# K0 Canonical Fact / History Contract V1

Status: CANDIDATE_FOUNDATION

## 1. Canonical Fact

Every Fact must carry:

    fact_type
    subject_id
    occurred_at                 caller supplied; no implicit clock
    canonical JSON payload
    source_id
    object_id / object_version
    environment_fingerprint
    schema_version
    non-empty evidence_refs
    prior_fact_refs             required only for correction / invalidation

FACT ID is SHA-256 over this canonical content with sorted JSON keys, UTF-8
encoding and no non-finite numeric values. Evidence and prior-Fact references
are treated as canonical sets, while timezone-aware timestamps are normalized
to UTC. Renaming a JSON key, changing provenance, evidence membership,
timestamp instant or payload changes identity. Reordering JSON mapping keys or
reference sets does not.

## 2. Append-only History

FactHistory is an immutable ordered tuple of admitted Facts. Its history ID
hashes the ordered Fact IDs. The only public ledger mutation is:

    append(fact, expected_history_id)

The expected identity is an optimistic-concurrency guard. A writer holding an
old History identity receives StaleHistoryError and must read again; it cannot
silently append to an obsolete branch. There is no public update, delete,
write_state, set_state, execute or recover API.

## 3. Correction and invalidation

Correction and invalidation require references to already-admitted Facts. The
target Fact remains in History. derive_fact_resolution(history) is a
deterministic projection that labels it SUPERSEDED or INVALIDATED; it does not
alter the original Fact bytes.

## 4. Candidate non-interference

A CandidateProposal is not an admitted Fact and has no State API. A decision
about it becomes a decision Fact containing:

    candidate id/hash
    decision and reason
    state reference
    evidence and constraint references
    policy and authority reference
    compiler/schema/evidence-policy/policy version tuple
    effect = AUDIT_ONLY_NO_STATE_MUTATION

Consequently a DENY supplies auditable History but cannot directly apply a
transition. K1 may later derive a State consequence from that Decision Fact
under a separately authorized, versioned compiler.

## 5. Deferred kernel capabilities

K0 does not define Authoritative State, a State Compiler, normal/recovery
feasible regions, authority grants, execution, or external effects. Those are
separate K1/K2/K3 Gates and require fresh controller approval.

## 6. Acceptance evidence

The test suite verifies canonical identity, immutable Fact fields, duplicate
rejection, correction/invalidation append rules, stale-writer rejection,
deterministic replay and rejected-candidate non-interference. The independent
verifier additionally checks the public API surface and writes a source-hash
receipt.
