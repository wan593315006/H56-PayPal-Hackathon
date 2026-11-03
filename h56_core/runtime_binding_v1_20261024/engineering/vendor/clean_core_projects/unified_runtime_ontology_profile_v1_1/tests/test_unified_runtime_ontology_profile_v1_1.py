import copy
import hashlib
from pathlib import Path
import sys

import pytest

from unified_runtime_ontology_profile import (
    OntologyProfileError,
    RuntimeOntologyProfile,
    compare_profiles,
    default_profile_mapping,
    load_default_profile,
)


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from verify_ontology_alignment_audit_binding import verify_audit_binding  # noqa: E402


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def raw_profile():
    return copy.deepcopy(default_profile_mapping())


def resign(value):
    body = {key: value[key] for key in value if key != "profile_hash"}
    value["profile_hash"] = RuntimeOntologyProfile.expected_hash(body)
    return value


def descriptor(**overrides):
    value = {
        "object_type": "uro:Task",
        "source_id": "SOURCE:CANDIDATE:V1",
        "source_version": "1.0.0",
        "source_hash": digest("source"),
        "context_dimension_hashes": {
            "state_pattern": digest("state-pattern"),
            "policy_version": digest("policy-version"),
        },
    }
    value.update(overrides)
    return value


def test_default_profile_is_deterministic_and_content_bound():
    first = load_default_profile()
    second = load_default_profile()
    first.verify_identity()
    assert first.to_mapping() == second.to_mapping()
    assert first.profile_hash == second.profile_hash


def test_profile_contains_exactly_the_ten_core_terms_and_eight_dimensions():
    profile = load_default_profile()
    assert len(profile.core_terms) == 10
    assert len(profile.context_dimensions) == 8
    assert profile.core_terms["Task"] == "uro:Task"


def test_unknown_profile_field_fails_closed():
    value = raw_profile()
    value["registry_url"] = "forbidden"
    with pytest.raises(OntologyProfileError, match="PROFILE_UNKNOWN_FIELD"):
        RuntimeOntologyProfile.from_mapping(value)


def test_core_term_reinterpretation_fails_closed_even_if_hash_is_recomputed():
    value = raw_profile()
    value["core_terms"]["Task"] = "uro:WorkItem"
    with pytest.raises(OntologyProfileError, match="PROFILE_CORE_SEMANTIC_ID_MISMATCH"):
        RuntimeOntologyProfile.from_mapping(resign(value))


def test_unknown_extension_namespace_and_cross_namespace_term_fail_closed():
    value = raw_profile()
    value["extension_profiles"][0]["namespace"] = "uro-plugin"
    with pytest.raises(OntologyProfileError, match="EXTENSION_PROFILE_UNKNOWN_NAMESPACE"):
        RuntimeOntologyProfile.from_mapping(resign(value))
    value = raw_profile()
    value["extension_profiles"][0]["terms"][0] = "uro-method:ForgedTerm"
    value["extension_profiles"][0]["terms"] = sorted(value["extension_profiles"][0]["terms"])
    with pytest.raises(OntologyProfileError, match="EXTENSION_PROFILE_TERM_NAMESPACE_OR_DUPLICATE"):
        RuntimeOntologyProfile.from_mapping(resign(value))


def test_unknown_relation_type_and_invalid_semantic_fields_fail_closed():
    value = raw_profile()
    value["relations"][0]["source_type"] = "uro:Unknown"
    with pytest.raises(OntologyProfileError, match="RELATION_UNKNOWN_SOURCE_OR_TARGET_TYPE"):
        RuntimeOntologyProfile.from_mapping(resign(value))
    value = raw_profile()
    value["relations"][0]["cardinality"] = "ANY"
    with pytest.raises(OntologyProfileError, match="RELATION_INVALID_CARDINALITY"):
        RuntimeOntologyProfile.from_mapping(resign(value))


def test_relation_order_and_duplicate_identity_fail_closed():
    value = raw_profile()
    value["relations"] = list(reversed(value["relations"]))
    with pytest.raises(OntologyProfileError, match="PROFILE_RELATIONS_NOT_SORTED"):
        RuntimeOntologyProfile.from_mapping(resign(value))
    value = raw_profile()
    value["relations"].append(copy.deepcopy(value["relations"][0]))
    value["relations"] = sorted(value["relations"], key=lambda item: item["relation_id"])
    with pytest.raises(OntologyProfileError, match="PROFILE_DUPLICATE_RELATION_ID"):
        RuntimeOntologyProfile.from_mapping(resign(value))


def test_unknown_or_mutated_context_dimension_fails_closed():
    profile = load_default_profile()
    with pytest.raises(OntologyProfileError, match="READ_ONLY_DESCRIPTOR_UNKNOWN_CONTEXT_DIMENSION"):
        profile.describe(descriptor(context_dimension_hashes={"unknown": digest("x")}))
    value = raw_profile()
    value["context_dimensions"] = value["context_dimensions"][:-1]
    with pytest.raises(OntologyProfileError, match="PROFILE_CONTEXT_DIMENSION_SET_MISMATCH"):
        RuntimeOntologyProfile.from_mapping(resign(value))


def test_read_only_descriptor_is_deterministic_and_rejects_unknown_object_type():
    profile = load_default_profile()
    first = profile.describe(descriptor())
    second = profile.describe(descriptor())
    assert first.to_mapping() == second.to_mapping()
    with pytest.raises(OntologyProfileError, match="READ_ONLY_DESCRIPTOR_UNKNOWN_OBJECT_TYPE"):
        profile.describe(descriptor(object_type="uro:Commit"))


def test_descriptor_contains_no_state_authority_commit_or_execution_field():
    profile = load_default_profile()
    for forbidden in ("state", "authority", "commit", "execution", "registry"):
        value = descriptor()
        value[forbidden] = "FORGED"
        with pytest.raises(OntologyProfileError, match="READ_ONLY_DESCRIPTOR_UNKNOWN_FIELD"):
            profile.describe(value)


def test_profile_hash_detects_hidden_relation_mutation():
    value = raw_profile()
    value["relations"][0]["forbidden_inference"] = "forged reinterpretation"
    with pytest.raises(OntologyProfileError, match="PROFILE_HASH_MISMATCH"):
        RuntimeOntologyProfile.from_mapping(value)


def test_profile_compatibility_never_performs_migration():
    base = load_default_profile()
    assert compare_profiles(base, base) == "COMPATIBLE"
    changed = raw_profile()
    changed["context_dimensions"] = list(reversed(changed["context_dimensions"]))
    changed["context_dimensions"] = sorted(changed["context_dimensions"])
    changed["relations"][0]["temporal_form"] = "INTERVAL"
    candidate = RuntimeOntologyProfile.from_mapping(resign(changed))
    assert compare_profiles(base, candidate) == "MIGRATION_REQUIRED"
    incompatible = raw_profile()
    incompatible["core_terms"]["Task"] = "uro:WorkItem"
    incompatible["profile_hash"] = "0" * 64
    with pytest.raises(OntologyProfileError):
        RuntimeOntologyProfile.from_mapping(incompatible)


def test_v1_1_recomputes_its_read_only_ontology_audit_predecessor_binding():
    result = verify_audit_binding()
    assert result["result"] == "PASS_ONTOLOGY_ALIGNMENT_AUDIT_BINDING"
