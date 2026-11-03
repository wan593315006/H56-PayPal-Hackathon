"""Pure, candidate-only capability definition contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Tuple


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$")
_IDENTITY = re.compile(r"^[A-Z][A-Z0-9:_-]{2,127}$")
_ALLOWED_RISK = frozenset({"LOW", "MEDIUM", "HIGH"})
_ALLOWED_EXTENSIONS = frozenset({"CORE", "DATA", "METHOD", "RESOURCE"})


class CapabilityContractError(ValueError):
    """Raised when a candidate capability declaration is malformed or drifts."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value.keys())
    unknown = actual - expected
    missing = expected - actual
    if unknown:
        raise CapabilityContractError("%s_UNKNOWN_FIELD:%s" % (label, ",".join(sorted(unknown))))
    if missing:
        raise CapabilityContractError("%s_MISSING_FIELD:%s" % (label, ",".join(sorted(missing))))


def _require_identity(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTITY.fullmatch(value):
        raise CapabilityContractError("%s_INVALID_IDENTITY" % label)
    return value


def _require_version(value: str, label: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise CapabilityContractError("%s_INVALID_VERSION" % label)
    return value


def _require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CapabilityContractError("%s_INVALID_SHA256" % label)
    return value


@dataclass(frozen=True)
class ContractDescriptor:
    """A typed, content-bound descriptor without a resolver or adapter."""

    schema_id: str
    schema_version: str
    schema_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], label: str) -> "ContractDescriptor":
        if not isinstance(value, Mapping):
            raise CapabilityContractError("%s_NOT_A_MAPPING" % label)
        _require_exact_keys(value, frozenset({"schema_id", "schema_version", "schema_hash"}), label)
        return cls(
            schema_id=_require_identity(value["schema_id"], label + "_SCHEMA_ID"),
            schema_version=_require_version(value["schema_version"], label + "_SCHEMA_VERSION"),
            schema_hash=_require_sha256(value["schema_hash"], label + "_SCHEMA_HASH"),
        )

    def to_mapping(self) -> Mapping[str, str]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "schema_hash": self.schema_hash,
        }


@dataclass(frozen=True)
class CapabilityDefinition:
    """A deterministic public declaration of what one Capability is.

    The type deliberately contains no present-availability, permission,
    authority, commit, executor or tool reference.
    """

    capability_id: str
    version: str
    input_contract: ContractDescriptor
    output_contract: ContractDescriptor
    precondition_hash: str
    scope_hash: str
    risk_class: str
    resource_requirement_hash: str
    failure_boundary_hash: str
    observation_requirement_hash: str
    source_id: str
    source_version: str
    source_hash: str
    extension_profile: str
    definition_hash: str

    _FIELDS = frozenset(
        {
            "capability_id",
            "version",
            "input_contract",
            "output_contract",
            "precondition_hash",
            "scope_hash",
            "risk_class",
            "resource_requirement_hash",
            "failure_boundary_hash",
            "observation_requirement_hash",
            "source_id",
            "source_version",
            "source_hash",
            "extension_profile",
            "definition_hash",
        }
    )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CapabilityDefinition":
        if not isinstance(value, Mapping):
            raise CapabilityContractError("CAPABILITY_DEFINITION_NOT_A_MAPPING")
        _require_exact_keys(value, cls._FIELDS, "CAPABILITY_DEFINITION")
        risk = value["risk_class"]
        profile = value["extension_profile"]
        if risk not in _ALLOWED_RISK:
            raise CapabilityContractError("CAPABILITY_DEFINITION_INVALID_RISK_CLASS")
        if profile not in _ALLOWED_EXTENSIONS:
            raise CapabilityContractError("CAPABILITY_DEFINITION_UNKNOWN_EXTENSION_PROFILE")
        body = {
            "capability_id": _require_identity(value["capability_id"], "CAPABILITY"),
            "version": _require_version(value["version"], "CAPABILITY"),
            "input_contract": ContractDescriptor.from_mapping(value["input_contract"], "INPUT_CONTRACT"),
            "output_contract": ContractDescriptor.from_mapping(value["output_contract"], "OUTPUT_CONTRACT"),
            "precondition_hash": _require_sha256(value["precondition_hash"], "PRECONDITION"),
            "scope_hash": _require_sha256(value["scope_hash"], "SCOPE"),
            "risk_class": risk,
            "resource_requirement_hash": _require_sha256(value["resource_requirement_hash"], "RESOURCE_REQUIREMENT"),
            "failure_boundary_hash": _require_sha256(value["failure_boundary_hash"], "FAILURE_BOUNDARY"),
            "observation_requirement_hash": _require_sha256(value["observation_requirement_hash"], "OBSERVATION_REQUIREMENT"),
            "source_id": _require_identity(value["source_id"], "SOURCE"),
            "source_version": _require_version(value["source_version"], "SOURCE"),
            "source_hash": _require_sha256(value["source_hash"], "SOURCE"),
            "extension_profile": profile,
        }
        expected = canonical_sha256(cls._body_mapping(body))
        supplied = _require_sha256(value["definition_hash"], "DEFINITION")
        if supplied != expected:
            raise CapabilityContractError("CAPABILITY_DEFINITION_HASH_MISMATCH")
        return cls(definition_hash=supplied, **body)

    @staticmethod
    def _body_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
        body = dict(value)
        for name in ("input_contract", "output_contract"):
            descriptor = body[name]
            body[name] = descriptor.to_mapping() if isinstance(descriptor, ContractDescriptor) else descriptor
        return body

    @classmethod
    def expected_hash(cls, body: Mapping[str, Any]) -> str:
        return canonical_sha256(cls._body_mapping(body))

    def body_mapping(self) -> Mapping[str, Any]:
        return self._body_mapping(
            {
                "capability_id": self.capability_id,
                "version": self.version,
                "input_contract": self.input_contract,
                "output_contract": self.output_contract,
                "precondition_hash": self.precondition_hash,
                "scope_hash": self.scope_hash,
                "risk_class": self.risk_class,
                "resource_requirement_hash": self.resource_requirement_hash,
                "failure_boundary_hash": self.failure_boundary_hash,
                "observation_requirement_hash": self.observation_requirement_hash,
                "source_id": self.source_id,
                "source_version": self.source_version,
                "source_hash": self.source_hash,
                "extension_profile": self.extension_profile,
            }
        )

    def to_mapping(self) -> Mapping[str, Any]:
        value = dict(self.body_mapping())
        value["definition_hash"] = self.definition_hash
        return value

    def verify_identity(self) -> None:
        if self.definition_hash != self.expected_hash(self.body_mapping()):
            raise CapabilityContractError("CAPABILITY_DEFINITION_IDENTITY_DRIFT")
