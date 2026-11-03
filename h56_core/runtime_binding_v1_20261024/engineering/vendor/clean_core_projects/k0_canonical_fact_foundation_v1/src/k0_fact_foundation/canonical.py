"""Canonical encoding used by K0 identities. No implicit clock or random ID."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ContractViolation(ValueError):
    """A value violates the frozen K0 candidate contract."""


def canonical_json(value: Any) -> str:
    """Return a stable JSON representation or fail closed for non-JSON values."""
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ContractViolation("value is not canonical JSON") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{field} must be non-empty text")
    return value.strip()


def require_text_tuple(values: tuple[str, ...], field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ContractViolation(f"{field} must be a tuple")
    normalized = tuple(require_text(value, field) for value in values)
    if not allow_empty and not normalized:
        raise ContractViolation(f"{field} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ContractViolation(f"{field} must not contain duplicates")
    return tuple(sorted(normalized))


def require_timestamp(value: str, field: str) -> str:
    """Accept an explicit timezone-aware ISO-8601 timestamp and normalize UTC."""
    value = require_text(value, field)
    parseable = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise ContractViolation(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ContractViolation(f"{field} must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat().replace("+00:00", "Z")
