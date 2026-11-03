# Candidate Capability Feasibility Projection V0.1

This project evaluates the declared candidate feasibility of one or more
Capabilities against a frozen Task, State, Method, Policy, Authority, Budget
and Evidence context.

```text
Definition + declared context -> Candidate Feasibility Projection
Candidate Feasibility Projections + one context -> Candidate CapabilityFeasibleSet
```

It is deliberately not a capability resolver, tool registry, source-trust
verifier, Authority issuer, Commit path or executor.

## Current truth

```ini
CAPABILITY_FEASIBILITY = CANDIDATE_DECLARATION_CONSISTENCY_ONLY
CAPABILITY_FEASIBLE_SET = CANDIDATE_PLANNING_ONLY
REAL_CAPABILITY_AVAILABILITY = NOT_ESTABLISHED
REAL_AUTHORITY = NOT_ESTABLISHED
FEASIBLE = CANDIDATE_PLANNING_ONLY
AUTHORITY_OR_COMMIT = NOT_IMPLEMENTED
TOOL_OR_EXTERNAL_EXECUTION = NOT_IMPLEMENTED
```

An all-caller-constructed input set can prove only that its frozen
declarations are internally consistent. It cannot prove that a tool, source,
budget, policy or Authority exists in reality.

## Native test commands

From this project directory:

```powershell
$env:PYTHONPATH = "src"
py -3.9 -m pytest -q
py -3.13 -m pytest -q
py -3.9 tools\audit_candidate_capability_feasibility_projection_v0_1_boundary.py
py -3.13 tools\audit_candidate_capability_feasibility_projection_v0_1_boundary.py
py -3.9 tools\verify_c1_canonical_capability_contract_binding.py
py -3.13 tools\verify_c1_canonical_capability_contract_binding.py
py -3.9 tools\build_candidate_capability_feasibility_projection_v0_1_manifest.py
py -3.13 tools\verify_candidate_capability_feasibility_projection_v0_1_manifest.py
```
