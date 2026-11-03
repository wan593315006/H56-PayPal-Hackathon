"""Fixed same-product assets and bounded byte provenance; no plug-ins."""
from pathlib import Path
from runtime_windows.source_identity import _read_checked, _root, _safe_name, parse_public_lock
from .contracts import FIELDS, decode, exact, need, raw_sha, sha, validate_boundary, VERSION

ASSET_NAMES = ("environment_policy.json", "state_mapping.json", "capability_catalog.json")
ASSUMPTION = dict(scope="SYNTHETIC_CANDIDATE_ASSUMPTION_ONLY",
                  authority_state="DECLARED_SUFFICIENT", authority_granted=False,
                  execution_permitted=False)
CAPABILITY = "CAP:ENV_QUALIFY_SIMULATED_TASK"
SELF_MEMBERS = ("__init__.py", "contracts.py", "assets.py", "evidence.py",
    "core_bridge.py", "assessment.py", "records.py", "cli.py", "assets/manifest.json",
    "assets/environment_policy.json", "assets/state_mapping.json", "assets/capability_catalog.json",
    "fixtures/cases.json", "tests/test_evidence.py", "tests/test_core_chain.py",
    "tests/test_records.py", "tests/test_boundary.py", "README.md")
SUPPORT_MEMBERS = ("__init__.py", "errors.py", "paths.py", "source_identity.py",
    "runtime_admission.py", "assembly/__init__.py", "assembly/contracts.py",
    "adapters/__init__.py", "adapters/bounded_rules.py", "task_store.py", "public-source-lock.json")

def read_bytes(path, maximum=1048576, size=None):
    path = Path(path)
    _root(path.parent)  # Reject relative/UNC/traversal before accessing leaf.
    return _read_checked(path, size, maximum)

def source_manifest(expected_sha):
    path = Path(__file__).absolute().parent / "SOURCE_MANIFEST.json"
    raw = read_bytes(path)
    need(raw_sha(raw) == sha(expected_sha), "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    obj = decode(raw, 1048576)
    exact(obj, ("schema", "interface_version", "runtime_required", "provenance_only"))
    need(obj["schema"] == "H56_OFFLINE_SOURCE_MANIFEST_V1" and
         obj["interface_version"] == VERSION and len(obj["runtime_required"]) == 139,
         "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    product = _root(path.parent.parent)
    lock_raw = read_bytes(product / "runtime_windows" / "public-source-lock.json")
    need(raw_sha(lock_raw) == "060bbaa1976d243b9441a295c889fdf5dfa2252db66381ae669e6f5804ff07e3",
         "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    lock = parse_public_lock(lock_raw)
    expected_names = {"offline_qualification_v1/" + n for n in SELF_MEMBERS}
    expected_names.update("runtime_windows/" + n for n in SUPPORT_MEMBERS)
    expected_names.update("runtime_binding_v1_20261024/engineering/vendor/" + n for n in lock["vendor"])
    need({m["path"] for m in obj["runtime_required"]} == expected_names,
         "SOURCE_MEMBER_SCOPE_MISMATCH", "SOURCE")
    names = set()
    total = 0
    for member in obj["runtime_required"]:
        exact(member, ("path", "size", "sha256"))
        name = member["path"]
        parts = _safe_name(name)
        need(name.casefold() not in names and type(member["size"]) is int and
             0 <= member["size"] <= 1048576, "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
        names.add(name.casefold())
        total += member["size"]
        need(total <= 8 * 1024 * 1024, "SOURCE_TOTAL_BYTE_BUDGET", "SOURCE")
        body = read_bytes(product.joinpath(*parts), size=member["size"])
        need(raw_sha(body) == sha(member["sha256"]), "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    # Provenance-only identities never cause filesystem reads or imports.
    return product, obj

def load_assets(expected_manifest_sha):
    root = _root(Path(__file__).absolute().parent / "assets")
    raw = read_bytes(root / "manifest.json")
    need(raw_sha(raw) == sha(expected_manifest_sha), "ENV_SOURCE_OR_VERSION_MISMATCH", "ASSETS")
    manifest = decode(raw, 1048576)
    exact(manifest, ("schema", "interface_version", "namespace", "members"))
    need(manifest["schema"] == "H56_ENV_ASSET_MANIFEST_V1" and
         manifest["interface_version"] == VERSION and
         manifest["namespace"] == "ENV_QUALIFICATION_V1", "ENV_SOURCE_OR_VERSION_MISMATCH")
    need(type(manifest["members"]) is list and len(manifest["members"]) == 3,
         "ENV_SOURCE_OR_VERSION_MISMATCH")
    values, hashes = {}, {}
    for entry in manifest["members"]:
        exact(entry, ("path", "size", "sha256"))
        name = entry["path"]
        need(name in ASSET_NAMES and name not in values, "ENV_SOURCE_OR_VERSION_MISMATCH")
        need(type(entry["size"]) is int and 0 < entry["size"] <= 1048576, "INPUT_DATA_BUDGET")
        body = read_bytes(root / name, size=entry["size"])
        need(raw_sha(body) == sha(entry["sha256"]), "ENV_SOURCE_OR_VERSION_MISMATCH")
        values[name] = decode(body, 1048576)
        hashes[name] = entry["sha256"]
    need(set(values) == set(ASSET_NAMES), "ENV_SOURCE_OR_VERSION_MISMATCH")
    p, m, c = (values[n] for n in ASSET_NAMES)
    exact(p, ("schema", "interface_version", "role", "ttl_seconds", "required_fields",
              "version_tuple", "method_declaration", "synthetic_assumption", "budget_declaration",
              "identity_preimages", "boundary"), "ENV_SOURCE_OR_VERSION_MISMATCH")
    exact(m, ("schema", "interface_version", "state_pattern", "policy_expression",
              "rule_node_count", "max_nodes", "max_depth", "policy_to_C2", "context_producers"),
          "ENV_SOURCE_OR_VERSION_MISMATCH")
    exact(c, ("schema", "interface_version", "catalog_id", "catalog_version",
              "contract_project_id", "contract_commit", "contract_manifest_sha256",
              "definition_body", "availability_body", "materialization"),
          "ENV_SOURCE_OR_VERSION_MISMATCH")
    need((p["schema"], m["schema"], c["schema"]) == ("H56_ENV_POLICY_V1",
         "H56_ENV_STATE_MAPPING_V1", "H56_ENV_CAPABILITY_ASSET_V1"),
         "ENV_SOURCE_OR_VERSION_MISMATCH")
    need(p["interface_version"] == m["interface_version"] == c["interface_version"] == VERSION,
         "ENV_SOURCE_OR_VERSION_MISMATCH")
    validate_boundary(p["boundary"])
    need(p["role"] == "SIMULATED_OPERATOR_METADATA_HOST" and p["ttl_seconds"] == 300 and
         type(p["ttl_seconds"]) is int and p["required_fields"] == list(FIELDS) and
         p["method_declaration"] == dict(method_id="METHOD:ENV_QUALIFICATION_V1",
             version="1.0.0", scope="OFFLINE_SYNTHETIC_CANDIDATE_ONLY") and
         p["version_tuple"] == dict(compiler_version="K1:STATE_COMPILER:V1",
             schema_version="1.0.0", evidence_policy_version="1.0.0", policy_version="1.0.0") and
         type(p["budget_declaration"]["available_units"]) is int and
         p["budget_declaration"]["available_units"] == 1 and
         p["synthetic_assumption"] == ASSUMPTION and
         p["synthetic_assumption"]["authority_granted"] is False and
         p["synthetic_assumption"]["execution_permitted"] is False, "ENV_SOURCE_OR_VERSION_MISMATCH")
    need(m["state_pattern"] == "ENV_EVALUATION_V1" and
         m["policy_to_C2"] == {"true":"DECLARED_ALLOWED", "false":"DECLARED_DENIED",
                               "null":"DECLARED_UNKNOWN"} and
         c["catalog_version"] == "1.0.0" and c["definition_body"]["version"] == "1.0.0" and
         c["contract_project_id"] == "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1" and
         type(c["availability_body"]["minimum_budget_units"]) is int and
         c["availability_body"]["minimum_budget_units"] == 1 and
         c["definition_body"]["capability_id"] == CAPABILITY and
         c["catalog_id"] == "CATALOG:ENV_QUALIFICATION_V1" and
         c["contract_commit"] == "b01fa57f22c108e60ab26b1b285417d50f62b10c" and
         c["contract_manifest_sha256"] == "9ed5f996152a4de096206a54f09e9d6b8b2866a5ef2593cd1a9c619ea2e0c723",
         "ENV_SOURCE_OR_VERSION_MISMATCH")
    return dict(policy=p, mapping=m, capability=c, hashes=hashes,
                manifest_sha256=expected_manifest_sha)
