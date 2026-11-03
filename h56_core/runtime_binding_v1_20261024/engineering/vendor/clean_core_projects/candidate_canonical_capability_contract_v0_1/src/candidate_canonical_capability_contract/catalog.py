"""Immutable candidate catalog for canonical Capability Definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from .contracts import CapabilityContractError, CapabilityDefinition, _require_identity, _require_sha256, _require_version, canonical_sha256


@dataclass(frozen=True)
class CanonicalCapabilityCatalog:
    """A hash-bound definition snapshot, never a live pool or resolver."""

    catalog_id: str
    catalog_version: str
    definitions: Tuple[CapabilityDefinition, ...]
    catalog_hash: str

    _FIELDS = frozenset({"catalog_id", "catalog_version", "definitions", "catalog_hash"})

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CanonicalCapabilityCatalog":
        if not isinstance(value, Mapping):
            raise CapabilityContractError("CAPABILITY_CATALOG_NOT_A_MAPPING")
        actual = frozenset(value.keys())
        if actual != cls._FIELDS:
            unknown = actual - cls._FIELDS
            missing = cls._FIELDS - actual
            if unknown:
                raise CapabilityContractError("CAPABILITY_CATALOG_UNKNOWN_FIELD:%s" % ",".join(sorted(unknown)))
            raise CapabilityContractError("CAPABILITY_CATALOG_MISSING_FIELD:%s" % ",".join(sorted(missing)))
        raw_definitions = value["definitions"]
        if not isinstance(raw_definitions, list) or not raw_definitions:
            raise CapabilityContractError("CAPABILITY_CATALOG_DEFINITIONS_REQUIRED")
        definitions = tuple(CapabilityDefinition.from_mapping(item) for item in raw_definitions)
        identifiers = tuple(item.capability_id for item in definitions)
        if len(identifiers) != len(set(identifiers)):
            raise CapabilityContractError("CAPABILITY_CATALOG_DUPLICATE_CAPABILITY_ID")
        body = {
            "catalog_id": _require_identity(value["catalog_id"], "CATALOG"),
            "catalog_version": _require_version(value["catalog_version"], "CATALOG"),
            "definitions": [item.to_mapping() for item in definitions],
        }
        supplied = _require_sha256(value["catalog_hash"], "CATALOG")
        expected = canonical_sha256(body)
        if supplied != expected:
            raise CapabilityContractError("CAPABILITY_CATALOG_HASH_MISMATCH")
        return cls(
            catalog_id=body["catalog_id"],
            catalog_version=body["catalog_version"],
            definitions=definitions,
            catalog_hash=supplied,
        )

    @classmethod
    def expected_hash(cls, *, catalog_id: str, catalog_version: str, definitions: Tuple[CapabilityDefinition, ...]) -> str:
        return canonical_sha256(
            {
                "catalog_id": catalog_id,
                "catalog_version": catalog_version,
                "definitions": [item.to_mapping() for item in definitions],
            }
        )

    def to_mapping(self) -> Mapping[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "definitions": [item.to_mapping() for item in self.definitions],
            "catalog_hash": self.catalog_hash,
        }

    def require_definition(self, capability_id: str) -> CapabilityDefinition:
        for definition in self.definitions:
            if definition.capability_id == capability_id:
                return definition
        raise CapabilityContractError("CAPABILITY_CATALOG_UNKNOWN_CAPABILITY_ID")

    def verify_identity(self) -> None:
        for definition in self.definitions:
            definition.verify_identity()
        expected = self.expected_hash(
            catalog_id=self.catalog_id,
            catalog_version=self.catalog_version,
            definitions=self.definitions,
        )
        if expected != self.catalog_hash:
            raise CapabilityContractError("CAPABILITY_CATALOG_IDENTITY_DRIFT")
