# Candidate Canonical Capability Contract V0.1

This project establishes a source-bound, candidate-only common contract for
answering one question:

```text
What is this Capability?
```

It intentionally does **not** answer whether the Capability is available now,
authorised, committed, or executable.

## Current truth

```ini
CANONICAL_CAPABILITY_DEFINITION = CANDIDATE_CONTRACT_ONLY
CAPABILITY_AVAILABILITY = NOT_IMPLEMENTED
CAPABILITY_FEASIBLE_SET = NOT_IMPLEMENTED
AUTHORITY_OR_COMMIT_CREATION = NOT_IMPLEMENTED
TOOL_OR_EXTERNAL_EXECUTION = NOT_IMPLEMENTED
```

The contract accepts public declaration-shaped inputs only.  It imports no
legacy source project, resolves no tool, loads no plugin, reads no external
data and has no network, MCP, Provider, bus or Pipeline path.

## Native test commands

From this project directory:

```powershell
$env:PYTHONPATH = "src"
py -3.9 -m pytest -q
py -3.13 -m pytest -q
py -3.9 tools\audit_candidate_canonical_capability_contract_v0_1_boundary.py
py -3.13 tools\audit_candidate_canonical_capability_contract_v0_1_boundary.py
py -3.9 tools\verify_c0_unified_capability_pool_audit_binding.py
py -3.13 tools\verify_c0_unified_capability_pool_audit_binding.py
py -3.9 tools\build_candidate_canonical_capability_contract_v0_1_manifest.py
py -3.13 tools\verify_candidate_canonical_capability_contract_v0_1_manifest.py
py -3.9 tools\verify_candidate_canonical_capability_contract_v0_1_raw_git_identity.py --commit <frozen-commit>
py -3.13 tools\verify_candidate_canonical_capability_contract_v0_1_raw_git_identity.py --commit <frozen-commit>
```

The build command updates only this project's derived manifest.  The manifest
is an integrity receipt, not a Runtime registry or migration payload.
