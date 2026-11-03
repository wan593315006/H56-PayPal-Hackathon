# Unified Runtime Ontology Profile V1.1

This project freezes a **candidate, read-only semantic profile** for Runtime
objects.  It answers only:

```text
What type-level vocabulary, relation shape and version interpretation are
permitted for a candidate Runtime description?
```

## Current truth

```ini
UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1 = CANDIDATE_READ_ONLY_PROFILE_ONLY
CORE_AND_EXTENSION_SEMANTICS = CONTENT_BOUND_AND_FAIL_CLOSED
READ_ONLY_DESCRIPTOR_PROJECTION = VERIFIED_BY_CONTRACT_TEST_ONLY
ONTOLOGY_RUNTIME_OR_REGISTRY = NOT_IMPLEMENTED
STATE_HISTORY_RUNTIME_OR_FORMAL_MLM_WRITE = FORBIDDEN
LEGACY_ONTOLOGY_IMPORT_OR_CALL = FORBIDDEN
AUTHORITY_COMMIT_POLICY_EXECUTION = NOT_IMPLEMENTED
NETWORK_MCP_PROVIDER_BUS_PIPELINE = FORBIDDEN
```

The profile defines type-level semantic IDs.  It does not decide whether an
object instance is true, current, authorized, available or executable.

## Native tests

From this project directory:

```powershell
$env:PYTHONPATH = "src"
py -3.9 -m pytest -q
py -3.13 -m pytest -q
py -3.9 tools\audit_unified_runtime_ontology_profile_v1_1_boundary.py
py -3.13 tools\audit_unified_runtime_ontology_profile_v1_1_boundary.py
py -3.9 tools\verify_ontology_alignment_audit_binding.py
py -3.13 tools\verify_ontology_alignment_audit_binding.py
py -3.9 tools\review_with_five_body.py --output evidence\structured_review_py39.json
py -3.13 tools\review_with_five_body.py --output evidence\structured_review_py313.json
py -3.9 tools\verify_unified_runtime_ontology_profile_v1_1_manifest.py
py -3.13 tools\verify_unified_runtime_ontology_profile_v1_1_manifest.py
py -3.9 tools\verify_unified_runtime_ontology_profile_v1_1_raw_git_identity.py --commit <frozen-commit>
py -3.13 tools\verify_unified_runtime_ontology_profile_v1_1_raw_git_identity.py --commit <frozen-commit>
```

The semantic-review receipts must be byte-identical and have zero structural
issues.  The manifest is an integrity receipt.  It is not a migration payload
or a live semantic registry.
