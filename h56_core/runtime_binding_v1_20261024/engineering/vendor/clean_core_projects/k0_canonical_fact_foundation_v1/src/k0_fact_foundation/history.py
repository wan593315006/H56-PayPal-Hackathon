"""Functional append-only History and a small optimistic-concurrency ledger."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any

from .canonical import ContractViolation, content_hash
from .contracts import Fact


class StaleHistoryError(ContractViolation):
    """Writer observed a history identity that is no longer current."""


@dataclass(frozen=True)
class FactHistory:
    facts: tuple[Fact, ...]
    history_id: str

    @classmethod
    def empty(cls) -> "FactHistory":
        return cls(facts=(), history_id=cls._identity(()))

    @staticmethod
    def _identity(facts: tuple[Fact, ...]) -> str:
        return "HIST:" + content_hash({"contract_id": "K0:CANONICAL_HISTORY:V1", "fact_ids": [fact.fact_id for fact in facts]})

    def append(self, fact: Fact) -> "FactHistory":
        fact.verify()
        known = {item.fact_id for item in self.facts}
        if fact.fact_id in known:
            raise ContractViolation("duplicate Fact cannot be appended")
        missing_refs = set(fact.prior_fact_refs) - known
        if missing_refs:
            raise ContractViolation(f"prior Fact reference is not admitted: {sorted(missing_refs)}")
        next_facts = self.facts + (fact,)
        return FactHistory(facts=next_facts, history_id=self._identity(next_facts))

    def verify(self) -> None:
        replayed = FactHistory.empty()
        for fact in self.facts:
            replayed = replayed.append(fact)
        if replayed.history_id != self.history_id:
            raise ContractViolation("history_id does not match ordered Fact sequence")


@dataclass(frozen=True)
class AppendReceipt:
    previous_history_id: str
    history_id: str
    fact_id: str
    ordinal: int


class CanonicalFactLedger:
    """The only mutable object is the current pointer; admitted histories are immutable values."""

    def __init__(self, initial_history: FactHistory | None = None) -> None:
        self._history = initial_history or FactHistory.empty()
        self._history.verify()
        self._lock = threading.Lock()

    def read_history(self) -> FactHistory:
        return self._history

    def append(self, fact: Fact, *, expected_history_id: str) -> AppendReceipt:
        with self._lock:
            previous = self._history
            if expected_history_id != previous.history_id:
                raise StaleHistoryError("writer must re-read canonical history before appending")
            next_history = previous.append(fact)
            self._history = next_history
            return AppendReceipt(
                previous_history_id=previous.history_id,
                history_id=next_history.history_id,
                fact_id=fact.fact_id,
                ordinal=len(next_history.facts) - 1,
            )


def derive_fact_resolution(history: FactHistory) -> dict[str, dict[str, Any]]:
    """A deterministic projection: originals remain, later references alter only resolution."""
    history.verify()
    resolution: dict[str, dict[str, Any]] = {
        fact.fact_id: {"status": "ACTIVE", "resolved_by": None} for fact in history.facts
    }
    for fact in history.facts:
        if fact.fact_type == "correction":
            for target in fact.prior_fact_refs:
                resolution[target] = {"status": "SUPERSEDED", "resolved_by": fact.fact_id}
        elif fact.fact_type == "invalidation":
            for target in fact.prior_fact_refs:
                resolution[target] = {"status": "INVALIDATED", "resolved_by": fact.fact_id}
    return resolution
