"""Pure candidate State derivation; no Runtime, authority, or state writer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from k0_fact_foundation import FactHistory, VersionTuple, derive_fact_resolution
from k0_fact_foundation.canonical import ContractViolation, canonical_json, content_hash, require_text


STATE_COMPILER_CONTRACT_ID = "K1:STATE_COMPILER:V1"
STATE_PROJECTION_KEY = "state_projection"
STATE_CONTRIBUTING_FACT_TYPES = frozenset({"assertion", "correction"})


class StateCompilationError(ContractViolation):
    """The supplied History cannot produce an unambiguous candidate State."""


@dataclass(frozen=True)
class DerivedStateSnapshot:
    """Immutable projection of one History under one exact interpretation tuple."""

    snapshot_id: str
    history_id: str
    version_tuple: VersionTuple
    state_json: str
    contributing_fact_ids: tuple[str, ...]

    def state_by_subject(self) -> dict[str, dict[str, Any]]:
        """A decoded copy; callers cannot mutate snapshot bytes."""
        return json.loads(self.state_json)

    def provenance(self) -> dict[str, Any]:
        return {
            "history_ref": self.history_id,
            "compiler_version": self.version_tuple.compiler_version,
            "schema_version": self.version_tuple.schema_version,
            "evidence_policy_version": self.version_tuple.evidence_policy_version,
            "policy_version": self.version_tuple.policy_version,
            "contributing_fact_ids": list(self.contributing_fact_ids),
        }

    def verify(self) -> None:
        core = {
            "contract_id": STATE_COMPILER_CONTRACT_ID,
            "history_id": self.history_id,
            "version_tuple": self.version_tuple.to_dict(),
            "state": self.state_by_subject(),
            "contributing_fact_ids": list(self.contributing_fact_ids),
        }
        expected = "STATE:" + content_hash(core)
        if self.snapshot_id != expected:
            raise StateCompilationError("snapshot_id does not match canonical compilation output")


class StateCompiler:
    """Compiles only K0-admitted FactHistory values into candidate Snapshots."""

    def __init__(self, *, compiler_version: str = STATE_COMPILER_CONTRACT_ID) -> None:
        self._compiler_version = require_text(compiler_version, "compiler_version")

    def compile(self, history: FactHistory, version_tuple: VersionTuple) -> DerivedStateSnapshot:
        if version_tuple.compiler_version != self._compiler_version:
            raise StateCompilationError("version tuple compiler_version does not match this compiler")
        history.verify()
        resolution = derive_fact_resolution(history)
        state_by_subject: dict[str, dict[str, Any]] = {}
        contributing_fact_ids: list[str] = []

        for fact in history.facts:
            payload = fact.payload()
            has_projection = STATE_PROJECTION_KEY in payload
            if has_projection and fact.fact_type not in STATE_CONTRIBUTING_FACT_TYPES:
                raise StateCompilationError(
                    f"{fact.fact_type} Fact {fact.fact_id} is not allowed to carry a State projection"
                )
            if fact.fact_type not in STATE_CONTRIBUTING_FACT_TYPES:
                continue
            if resolution[fact.fact_id]["status"] != "ACTIVE":
                continue
            if not has_projection:
                continue
            projection = payload[STATE_PROJECTION_KEY]
            if not isinstance(projection, Mapping) or not projection:
                raise StateCompilationError("state_projection must be a non-empty mapping")
            subject_state = state_by_subject.setdefault(fact.subject_id, {})
            for raw_key, value in projection.items():
                key = require_text(str(raw_key), "state_projection key")
                try:
                    canonical_json(value)
                except ContractViolation as exc:
                    raise StateCompilationError("state_projection value is not canonical JSON") from exc
                if key in subject_state and canonical_json(subject_state[key]) != canonical_json(value):
                    raise StateCompilationError(
                        f"conflicting active projections for {fact.subject_id}.{key}"
                    )
                subject_state[key] = value
            contributing_fact_ids.append(fact.fact_id)

        state_json = canonical_json(state_by_subject)
        core = {
            "contract_id": STATE_COMPILER_CONTRACT_ID,
            "history_id": history.history_id,
            "version_tuple": version_tuple.to_dict(),
            "state": json.loads(state_json),
            "contributing_fact_ids": contributing_fact_ids,
        }
        snapshot = DerivedStateSnapshot(
            snapshot_id="STATE:" + content_hash(core),
            history_id=history.history_id,
            version_tuple=version_tuple,
            state_json=state_json,
            contributing_fact_ids=tuple(contributing_fact_ids),
        )
        snapshot.verify()
        return snapshot


class SnapshotCache:
    """Optional immutable Snapshot cache. It is never a source of History truth."""

    def __init__(self, compiler: StateCompiler) -> None:
        self._compiler = compiler
        self._snapshots: dict[tuple[str, str], DerivedStateSnapshot] = {}

    def derive(self, history: FactHistory, version_tuple: VersionTuple) -> DerivedStateSnapshot:
        snapshot = self._compiler.compile(history, version_tuple)
        cache_key = (snapshot.history_id, canonical_json(snapshot.version_tuple.to_dict()))
        cached = self._snapshots.get(cache_key)
        if cached is not None and cached.snapshot_id != snapshot.snapshot_id:
            raise StateCompilationError("cache identity disagrees with deterministic recompilation")
        self._snapshots[cache_key] = snapshot
        return snapshot

    def lookup(self, *, history_id: str, version_tuple: VersionTuple) -> DerivedStateSnapshot | None:
        """Lookup only; a cache miss must be resolved by compiling History again."""
        key = (require_text(history_id, "history_id"), canonical_json(version_tuple.to_dict()))
        return self._snapshots.get(key)
