from dataclasses import replace
import hashlib
from pathlib import Path
import sys

import pytest

from candidate_canonical_capability_contract import (
    CanonicalCapabilityCatalog,
    CapabilityContractError,
    CapabilityDefinition,
)


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from verify_c0_unified_capability_pool_audit_binding import (  # noqa: E402
    C0BindingError,
    load_binding,
    verify_c0_binding,
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def definition_body(**overrides):
    value = {
        "capability_id": "CAP:STRUCTURED_AUDIT:CAPTURE:V1",
        "version": "1.0.0",
        "input_contract": {
            "schema_id": "SCHEMA:TASK_INPUT:V1",
            "schema_version": "1.0.0",
            "schema_hash": digest("task-input-schema"),
        },
        "output_contract": {
            "schema_id": "SCHEMA:EVIDENCE_CAPTURE:V1",
            "schema_version": "1.0.0",
            "schema_hash": digest("evidence-capture-schema"),
        },
        "precondition_hash": digest("preconditions"),
        "scope_hash": digest("candidate-only-scope"),
        "risk_class": "LOW",
        "resource_requirement_hash": digest("bounded-resources"),
        "failure_boundary_hash": digest("failure-boundary"),
        "observation_requirement_hash": digest("observation-requirement"),
        "source_id": "SOURCE:V05_STATIC_CATALOG:V1",
        "source_version": "1.0.0",
        "source_hash": digest("v05-static-catalog-reference"),
        "extension_profile": "CORE",
    }
    value.update(overrides)
    return value


def definition(**overrides):
    body = definition_body(**overrides)
    body["definition_hash"] = CapabilityDefinition.expected_hash(body)
    return body


def catalog(definitions=None, **overrides):
    raw_definitions = definitions or [definition()]
    value = {
        "catalog_id": "CAPABILITY_CATALOG:CANDIDATE:V1",
        "catalog_version": "1.0.0",
        "definitions": raw_definitions,
    }
    value.update(overrides)
    parsed = tuple(CapabilityDefinition.from_mapping(item) for item in value["definitions"])
    value["catalog_hash"] = CanonicalCapabilityCatalog.expected_hash(
        catalog_id=value["catalog_id"], catalog_version=value["catalog_version"], definitions=parsed
    )
    return value


def test_definition_and_catalog_replay_are_deterministic():
    first = CanonicalCapabilityCatalog.from_mapping(catalog())
    second = CanonicalCapabilityCatalog.from_mapping(catalog())
    first.verify_identity()
    second.verify_identity()
    assert first.catalog_hash == second.catalog_hash
    assert first.definitions[0].definition_hash == second.definitions[0].definition_hash


def test_definition_keeps_definition_separate_from_present_availability():
    value = CapabilityDefinition.from_mapping(definition())
    assert not hasattr(value, "available_now")
    assert "availability" not in value.to_mapping()


def test_undeclared_availability_authority_and_execution_fields_fail_closed():
    for field in ("available_now", "authority", "commit", "execution", "tool_reference"):
        value = definition()
        value[field] = "FORGED"
        with pytest.raises(CapabilityContractError, match="CAPABILITY_DEFINITION_UNKNOWN_FIELD"):
            CapabilityDefinition.from_mapping(value)


def test_hidden_definition_mutation_reusing_old_hash_is_rejected():
    value = definition()
    value["scope_hash"] = digest("expanded-scope")
    with pytest.raises(CapabilityContractError, match="CAPABILITY_DEFINITION_HASH_MISMATCH"):
        CapabilityDefinition.from_mapping(value)


def test_unknown_extension_profile_fails_closed():
    value = definition(extension_profile="PLUGIN")
    value["definition_hash"] = CapabilityDefinition.expected_hash({key: value[key] for key in value if key != "definition_hash"})
    with pytest.raises(CapabilityContractError, match="UNKNOWN_EXTENSION_PROFILE"):
        CapabilityDefinition.from_mapping(value)


def test_malformed_source_hash_fails_closed():
    value = definition(source_hash="not-a-hash")
    value["definition_hash"] = "0" * 64
    with pytest.raises(CapabilityContractError, match="SOURCE_INVALID_SHA256"):
        CapabilityDefinition.from_mapping(value)


def test_duplicate_capability_identity_fails_closed_even_when_catalog_hash_is_recomputed():
    duplicate = definition()
    value = catalog(definitions=[definition(), duplicate])
    with pytest.raises(CapabilityContractError, match="DUPLICATE_CAPABILITY_ID"):
        CanonicalCapabilityCatalog.from_mapping(value)


def test_catalog_hash_binds_definition_order_and_content():
    second = definition(capability_id="CAP:STRUCTURED_AUDIT:EVALUATE:V1")
    value = catalog(definitions=[definition(), second])
    value["definitions"] = list(reversed(value["definitions"]))
    with pytest.raises(CapabilityContractError, match="CAPABILITY_CATALOG_HASH_MISMATCH"):
        CanonicalCapabilityCatalog.from_mapping(value)


def test_catalog_lookup_is_immutable_and_missing_identity_fails_closed():
    parsed = CanonicalCapabilityCatalog.from_mapping(catalog())
    assert parsed.require_definition("CAP:STRUCTURED_AUDIT:CAPTURE:V1").capability_id.endswith("CAPTURE:V1")
    with pytest.raises(CapabilityContractError, match="UNKNOWN_CAPABILITY_ID"):
        parsed.require_definition("CAP:NOT_DECLARED:V1")
    with pytest.raises(Exception):
        parsed.definitions += ()


def test_tampered_in_memory_definition_identity_is_detected():
    parsed = CapabilityDefinition.from_mapping(definition())
    with pytest.raises(CapabilityContractError, match="CAPABILITY_DEFINITION_IDENTITY_DRIFT"):
        replace(parsed, risk_class="HIGH").verify_identity()


def test_c0_audit_binding_is_recomputed_before_c1_regression():
    result = verify_c0_binding()
    assert result["result"] == "PASS_C0_AUDIT_BINDING"
    assert result["managed_file_count"] == 8


def test_c0_audit_binding_drift_fails_closed():
    binding = dict(load_binding())
    binding["audit_manifest_sha256"] = digest("forged-c0-manifest")
    with pytest.raises(C0BindingError, match="C0_AUDIT_MANIFEST_HASH_DRIFT"):
        verify_c0_binding(binding)
