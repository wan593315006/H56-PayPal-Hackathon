# K1 State Derivation Foundation V1 — Project Card

```text
task_id: CLEAN_CORE:K1_STATE_DERIVATION_FOUNDATION:V1
objective: Build and verify candidate-only deterministic State derivation from immutable K0 History plus one fixed version tuple.
task_type: construction
risk_tier: L2
controller_authorization: explicit controller authorization on 2026-09-25
predecessor: K0_PROJECT_MANIFEST.json SHA-256 6a1bb6959b8292b244097fe2827aa893286f53d4a42e958ae3285ba6cb156a38
legacy_role: READ_ONLY_ORACLE
write_scope: clean_core_projects/k1_state_derivation_foundation_v1/ and current control-plane entries
allowed_actions:
  - import K0 candidate contracts read-only
  - candidate State compiler, immutable Snapshot cache, standard-library tests
  - explicit no-side-effect BusinessSemanticCompiler and SoftwareWorldModelCompiler review
forbidden_actions:
  - modify K0, Legacy Five-Body, P10/P10R1/P11/P13 artifacts
  - Runtime write, formal MLM write, authority grant, governance transition, recovery transition or execution
  - wuti_bus.call, MCP, Provider, Pipeline, Executor or external side effect
required_verification:
  - Python 3.9 and 3.13 tests
  - same History plus same VersionTuple deterministic replay
  - version-sensitive provenance and identity
  - correction/invalidation projection behavior
  - conflict and malformed projection fail-closed behavior
  - Decision/Candidate non-interference
  - snapshot cache is not a source-of-truth API
pass_fail_blocked_criteria:
  - PASS: all declared K1 checks pass on both interpreters and no State/Runtime authority is exposed.
  - FAIL: direct State writer, versionless Snapshot, non-deterministic replay, candidate Decision state effect, or conflict auto-selection exists.
  - BLOCKED: K0 manifest cannot be verified or required candidate-only compiler cannot run safely.
requires_controller_decision: true, before K2, K3, legacy integration, or any Runtime/Authority use.
```

K1 produces a candidate DerivedStateSnapshot only. It does not establish a
production-authoritative State.
