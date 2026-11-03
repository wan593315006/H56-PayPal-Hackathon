"""Pure contracts for a read-only candidate Runtime Ontology profile."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Tuple


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_PROFILE_ID = re.compile(r"^URO:PROFILE:V[0-9_]+$")
_SEMANTIC_ID = re.compile(r"^uro(?:-[a-z]+)?:[A-Za-z][A-Za-z0-9]*$")
_CARDINALITIES = frozenset({"ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"})
_TEMPORAL_FORMS = frozenset({"ATEMPORAL", "POINT_IN_TIME", "INTERVAL", "EVENTUAL"})
_SCOPES = frozenset({"CANDIDATE_ONLY"})
_EVIDENCE_REQUIREMENTS = frozenset({"DECLARED", "SOURCE_BOUND", "REPLAYED"})
_CORE_TERMS = frozenset({"Task", "State", "Candidate", "Capability", "Method", "Observation", "Evidence", "Policy", "Authority", "Session"})
_EXTENSION_NAMESPACES = frozenset({"uro-data", "uro-method", "uro-trust", "uro-resource"})
_CONTEXT_DIMENSIONS = frozenset({"state_pattern", "input_characteristics", "environment_version", "capability_version", "policy_version", "evidence_quality", "resource_budget", "lifecycle"})


class OntologyProfileError(ValueError):
    """Raised when a profile or read-only descriptor is malformed or drifts."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value.keys())
    if actual - expected:
        raise OntologyProfileError("%s_UNKNOWN_FIELD:%s" % (label, ",".join(sorted(actual - expected))))
    if expected - actual:
        raise OntologyProfileError("%s_MISSING_FIELD:%s" % (label, ",".join(sorted(expected - actual))))


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise OntologyProfileError("%s_INVALID_SHA256" % label)
    return value


def _require_version(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise OntologyProfileError("%s_INVALID_VERSION" % label)
    return value


def _require_semantic_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SEMANTIC_ID.fullmatch(value):
        raise OntologyProfileError("%s_INVALID_SEMANTIC_ID" % label)
    return value


@dataclass(frozen=True)
class ExtensionProfile:
    namespace: str
    version: str
    terms: Tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExtensionProfile":
        _require_exact_keys(value, frozenset({"namespace", "version", "terms"}), "EXTENSION_PROFILE")
        namespace = value["namespace"]
        if namespace not in _EXTENSION_NAMESPACES:
            raise OntologyProfileError("EXTENSION_PROFILE_UNKNOWN_NAMESPACE")
        version = _require_version(value["version"], "EXTENSION_PROFILE")
        terms = value["terms"]
        if not isinstance(terms, list) or not terms or terms != sorted(terms):
            raise OntologyProfileError("EXTENSION_PROFILE_TERMS_NOT_SORTED_NONEMPTY_LIST")
        parsed = tuple(_require_semantic_id(item, "EXTENSION_PROFILE_TERM") for item in terms)
        if len(set(parsed)) != len(parsed) or any(not item.startswith(namespace + ":") for item in parsed):
            raise OntologyProfileError("EXTENSION_PROFILE_TERM_NAMESPACE_OR_DUPLICATE")
        return cls(namespace=namespace, version=version, terms=parsed)

    def to_mapping(self) -> Mapping[str, Any]:
        return {"namespace": self.namespace, "version": self.version, "terms": list(self.terms)}


@dataclass(frozen=True)
class RelationDefinition:
    relation_id: str
    source_type: str
    target_type: str
    cardinality: str
    temporal_form: str
    scope: str
    evidence_requirement: str
    forbidden_inference: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], known_types: frozenset[str]) -> "RelationDefinition":
        _require_exact_keys(
            value,
            frozenset({"relation_id", "source_type", "target_type", "cardinality", "temporal_form", "scope", "evidence_requirement", "forbidden_inference"}),
            "RELATION",
        )
        relation_id = _require_semantic_id(value["relation_id"], "RELATION")
        source_type = _require_semantic_id(value["source_type"], "RELATION_SOURCE")
        target_type = _require_semantic_id(value["target_type"], "RELATION_TARGET")
        if source_type not in known_types or target_type not in known_types:
            raise OntologyProfileError("RELATION_UNKNOWN_SOURCE_OR_TARGET_TYPE")
        if value["cardinality"] not in _CARDINALITIES:
            raise OntologyProfileError("RELATION_INVALID_CARDINALITY")
        if value["temporal_form"] not in _TEMPORAL_FORMS:
            raise OntologyProfileError("RELATION_INVALID_TEMPORAL_FORM")
        if value["scope"] not in _SCOPES:
            raise OntologyProfileError("RELATION_INVALID_SCOPE")
        if value["evidence_requirement"] not in _EVIDENCE_REQUIREMENTS:
            raise OntologyProfileError("RELATION_INVALID_EVIDENCE_REQUIREMENT")
        if not isinstance(value["forbidden_inference"], str) or not value["forbidden_inference"]:
            raise OntologyProfileError("RELATION_INVALID_FORBIDDEN_INFERENCE")
        return cls(
            relation_id=relation_id,
            source_type=source_type,
            target_type=target_type,
            cardinality=value["cardinality"],
            temporal_form=value["temporal_form"],
            scope=value["scope"],
            evidence_requirement=value["evidence_requirement"],
            forbidden_inference=value["forbidden_inference"],
        )

    def to_mapping(self) -> Mapping[str, str]:
        return {
            "relation_id": self.relation_id,
            "source_type": self.source_type,
            "target_type": self.target_type,
            "cardinality": self.cardinality,
            "temporal_form": self.temporal_form,
            "scope": self.scope,
            "evidence_requirement": self.evidence_requirement,
            "forbidden_inference": self.forbidden_inference,
        }


@dataclass(frozen=True)
class ReadOnlyOntologyDescriptor:
    semantic_type: str
    source_id: str
    source_version: str
    source_hash: str
    context_dimension_hashes: Mapping[str, str]
    descriptor_hash: str

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "semantic_type": self.semantic_type,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "source_hash": self.source_hash,
            "context_dimension_hashes": dict(self.context_dimension_hashes),
            "descriptor_hash": self.descriptor_hash,
        }


@dataclass(frozen=True)
class RuntimeOntologyProfile:
    profile_id: str
    profile_version: str
    core_terms: Mapping[str, str]
    extension_profiles: Tuple[ExtensionProfile, ...]
    relations: Tuple[RelationDefinition, ...]
    context_dimensions: Tuple[str, ...]
    profile_hash: str

    _FIELDS = frozenset({"profile_id", "profile_version", "core_terms", "extension_profiles", "relations", "context_dimensions", "profile_hash"})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RuntimeOntologyProfile":
        if not isinstance(value, Mapping):
            raise OntologyProfileError("PROFILE_NOT_A_MAPPING")
        _require_exact_keys(value, cls._FIELDS, "PROFILE")
        profile_id = value["profile_id"]
        if not isinstance(profile_id, str) or not _PROFILE_ID.fullmatch(profile_id):
            raise OntologyProfileError("PROFILE_INVALID_ID")
        profile_version = _require_version(value["profile_version"], "PROFILE")
        core_terms = value["core_terms"]
        if not isinstance(core_terms, Mapping) or frozenset(core_terms.keys()) != _CORE_TERMS:
            raise OntologyProfileError("PROFILE_CORE_TERM_SET_MISMATCH")
        parsed_core = {key: _require_semantic_id(core_terms[key], "PROFILE_CORE_TERM") for key in sorted(_CORE_TERMS)}
        expected_ids = {"uro:" + key for key in _CORE_TERMS}
        if set(parsed_core.values()) != expected_ids or len(set(parsed_core.values())) != len(parsed_core):
            raise OntologyProfileError("PROFILE_CORE_SEMANTIC_ID_MISMATCH")
        extension_values = value["extension_profiles"]
        if not isinstance(extension_values, list) or not extension_values:
            raise OntologyProfileError("PROFILE_EXTENSIONS_NOT_NONEMPTY_LIST")
        extensions = tuple(ExtensionProfile.from_mapping(item) for item in extension_values)
        if tuple(item.namespace for item in extensions) != tuple(sorted(item.namespace for item in extensions)):
            raise OntologyProfileError("PROFILE_EXTENSIONS_NOT_SORTED")
        if len({item.namespace for item in extensions}) != len(extensions):
            raise OntologyProfileError("PROFILE_DUPLICATE_EXTENSION_NAMESPACE")
        known_types = frozenset(parsed_core.values()) | frozenset(term for item in extensions for term in item.terms)
        relation_values = value["relations"]
        if not isinstance(relation_values, list) or not relation_values:
            raise OntologyProfileError("PROFILE_RELATIONS_NOT_NONEMPTY_LIST")
        relations = tuple(RelationDefinition.from_mapping(item, known_types) for item in relation_values)
        if tuple(item.relation_id for item in relations) != tuple(sorted(item.relation_id for item in relations)):
            raise OntologyProfileError("PROFILE_RELATIONS_NOT_SORTED")
        if len({item.relation_id for item in relations}) != len(relations):
            raise OntologyProfileError("PROFILE_DUPLICATE_RELATION_ID")
        dimensions = value["context_dimensions"]
        if not isinstance(dimensions, list) or tuple(dimensions) != tuple(sorted(dimensions)) or frozenset(dimensions) != _CONTEXT_DIMENSIONS:
            raise OntologyProfileError("PROFILE_CONTEXT_DIMENSION_SET_MISMATCH")
        body = {
            "profile_id": profile_id,
            "profile_version": profile_version,
            "core_terms": parsed_core,
            "extension_profiles": [item.to_mapping() for item in extensions],
            "relations": [item.to_mapping() for item in relations],
            "context_dimensions": list(dimensions),
        }
        profile_hash = _require_hash(value["profile_hash"], "PROFILE")
        if profile_hash != cls.expected_hash(body):
            raise OntologyProfileError("PROFILE_HASH_MISMATCH")
        return cls(
            profile_id=profile_id,
            profile_version=profile_version,
            core_terms=parsed_core,
            extension_profiles=extensions,
            relations=relations,
            context_dimensions=tuple(dimensions),
            profile_hash=profile_hash,
        )

    @staticmethod
    def expected_hash(body: Mapping[str, Any]) -> str:
        return canonical_sha256(body)

    def body_mapping(self) -> Mapping[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "core_terms": dict(self.core_terms),
            "extension_profiles": [item.to_mapping() for item in self.extension_profiles],
            "relations": [item.to_mapping() for item in self.relations],
            "context_dimensions": list(self.context_dimensions),
        }

    def to_mapping(self) -> Mapping[str, Any]:
        result = dict(self.body_mapping())
        result["profile_hash"] = self.profile_hash
        return result

    def verify_identity(self) -> None:
        if self.profile_hash != self.expected_hash(self.body_mapping()):
            raise OntologyProfileError("PROFILE_IDENTITY_DRIFT")

    def describe(self, value: Mapping[str, Any]) -> ReadOnlyOntologyDescriptor:
        expected = frozenset({"object_type", "source_id", "source_version", "source_hash", "context_dimension_hashes"})
        _require_exact_keys(value, expected, "READ_ONLY_DESCRIPTOR")
        object_type = _require_semantic_id(value["object_type"], "READ_ONLY_DESCRIPTOR_OBJECT")
        known_types = frozenset(self.core_terms.values()) | frozenset(term for item in self.extension_profiles for term in item.terms)
        if object_type not in known_types:
            raise OntologyProfileError("READ_ONLY_DESCRIPTOR_UNKNOWN_OBJECT_TYPE")
        source_id = value["source_id"]
        if not isinstance(source_id, str) or not source_id:
            raise OntologyProfileError("READ_ONLY_DESCRIPTOR_INVALID_SOURCE_ID")
        source_version = _require_version(value["source_version"], "READ_ONLY_DESCRIPTOR_SOURCE")
        source_hash = _require_hash(value["source_hash"], "READ_ONLY_DESCRIPTOR_SOURCE")
        dimensions = value["context_dimension_hashes"]
        if not isinstance(dimensions, Mapping) or frozenset(dimensions.keys()) - _CONTEXT_DIMENSIONS:
            raise OntologyProfileError("READ_ONLY_DESCRIPTOR_UNKNOWN_CONTEXT_DIMENSION")
        parsed_dimensions = {key: _require_hash(dimensions[key], "READ_ONLY_DESCRIPTOR_CONTEXT") for key in sorted(dimensions)}
        body = {
            "semantic_type": object_type,
            "source_id": source_id,
            "source_version": source_version,
            "source_hash": source_hash,
            "context_dimension_hashes": parsed_dimensions,
        }
        return ReadOnlyOntologyDescriptor(descriptor_hash=canonical_sha256(body), **body)


def compare_profiles(previous: RuntimeOntologyProfile, candidate: RuntimeOntologyProfile) -> str:
    """Return a declared interpretation outcome; never migrate an object."""
    if previous.profile_id != candidate.profile_id:
        return "UNSUPPORTED"
    if previous.core_terms != candidate.core_terms:
        return "UNSUPPORTED"
    if previous.profile_hash == candidate.profile_hash:
        return "COMPATIBLE"
    if previous.context_dimensions != candidate.context_dimensions:
        return "MIGRATION_REQUIRED"
    if previous.relations != candidate.relations or previous.extension_profiles != candidate.extension_profiles:
        return "MIGRATION_REQUIRED"
    return "AMBIGUOUS"
