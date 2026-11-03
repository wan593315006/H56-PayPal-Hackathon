"""Static candidate Profile V1.1 data loader; no registry or resolver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import RuntimeOntologyProfile


_PROFILE_PATH = Path(__file__).resolve().parent / "data" / "UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1.json"


def default_profile_mapping() -> Mapping[str, Any]:
    return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))


def load_default_profile() -> RuntimeOntologyProfile:
    return RuntimeOntologyProfile.from_mapping(default_profile_mapping())
