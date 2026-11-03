# K0 Canonical Fact Foundation V1 — Project Card

```text
task_id: CLEAN_CORE:K0_CANONICAL_FACT_FOUNDATION:V1
objective: Build and verify a candidate-only canonical Fact and append-only History foundation for the V0.1 Dynamic Constraint Kernel.
task_type: construction
risk_tier: L2
controller_authorization: explicit controller authorization on 2026-09-25
legacy_role: READ_ONLY_ORACLE
write_scope: clean_core_projects/k0_canonical_fact_foundation_v1/ and the two current control-plane panels
allowed_actions:
  - candidate-only source construction and standard-library tests in this project
  - static legacy evidence consumption
  - no-side-effect BusinessSemanticCompiler and SoftwareWorldModelCompiler review with an explicit source root
forbidden_actions:
  - modify Legacy Five-Body source or audit evidence
  - write or attach any legacy Runtime, formal MLM, Authority, Registry, state store or migration package
  - wuti_bus.call, MCP, Provider, Pipeline, Executor, external network call or production side effect
minimum_reading_set:
  - project_control_plane/AUDITS/V0_1_DYNAMIC_CONSTRAINT_KERNEL_GAP_AUDIT_20260925/GAP_MATRIX.md
  - project_control_plane/AUDITS/V0_1_DYNAMIC_CONSTRAINT_KERNEL_GAP_AUDIT_20260925/SPEC/V0_1_DYNAMIC_CONSTRAINT_KERNEL_SPEC.md
  - this project README and K0_REQUIREMENT.md
required_verification:
  - Python 3.9 and 3.13 tests
  - deterministic canonical ID and history replay checks
  - correction/invalidation append checks
  - stale-writer/concurrency boundary check
  - rejected-candidate non-interference check
  - five-body candidate semantic/software-world review with authority closed
pass_fail_blocked_criteria:
  - PASS: all K0 tests pass on both interpreters and the candidate review confirms no Runtime/MLM authority.
  - FAIL: any arbitrary update/delete path, mutable overwrite, unbound Fact, direct State API, or authority-opening behavior exists.
  - BLOCKED: required interpreter or safe candidate compiler cannot be executed within the declared boundary.
requires_controller_decision: true, before K1, any legacy integration, or any authority-bearing use.
```

K0 implements no `State`, `Transition`, `Feasible Region`, `Authority`,
`Recovery` or external execution. It is a candidate foundation whose only legal
evolution is `Fact -> canonical History`.
