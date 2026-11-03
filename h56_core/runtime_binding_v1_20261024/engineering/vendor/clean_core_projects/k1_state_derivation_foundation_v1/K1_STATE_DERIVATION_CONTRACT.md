# K1 Deterministic State Derivation Contract V1

Status: CANDIDATE_FOUNDATION

## Input and output

K1 accepts only:

    immutable K0 FactHistory
    one VersionTuple
    StateCompiler whose compiler_version exactly equals VersionTuple.compiler_version

It returns one immutable DerivedStateSnapshot:

    snapshot_id
    history_id
    compiler/schema/evidence-policy/policy versions
    canonical state JSON
    contributing Fact IDs

The Snapshot ID is the canonical hash of all five items. Thus the same History
and exact version tuple repeat to the same Snapshot, while any version change is
visible in provenance and Snapshot identity.

## Projection rules

- Only active assertion or correction Facts may contribute a non-empty
  state_projection mapping.
- Every other Fact type carrying state_projection is rejected. It is not
  silently ignored, even when the payload would have had no State effect.
- Superseded and invalidated Facts do not contribute.
- Two active facts assigning unequal canonical values to the same
  subject/key are a compilation error; newest-wins selection is forbidden.
- Decision, transition_proposed, and invalidation Facts must not carry a state
  projection. Such a History fails compilation rather than granting an
  indirect Candidate-to-State path.

## Snapshot cache

SnapshotCache can derive and lookup immutable snapshots keyed by History and
VersionTuple. It has no public put, update, delete or State write API. Every
derive operation recompiles the supplied History before it trusts an existing
cache entry. The cache is therefore an optimization, not a truth source.

## K1 boundary

K1 State is candidate-only and non-authoritative. K1 has no History append,
Runtime write, Authority, feasibility calculation, governance commit, recovery
or external execution. K2/K3 must be separately authorized.
