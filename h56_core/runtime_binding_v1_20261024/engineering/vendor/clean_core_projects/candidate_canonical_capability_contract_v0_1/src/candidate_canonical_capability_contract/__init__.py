"""Candidate-only canonical Capability Definition contract."""

from .catalog import CanonicalCapabilityCatalog
from .contracts import CapabilityContractError, CapabilityDefinition, ContractDescriptor

__all__ = [
    "CanonicalCapabilityCatalog",
    "CapabilityContractError",
    "CapabilityDefinition",
    "ContractDescriptor",
]
