"""Private immutable assessment storage; reuses the existing TaskJournal."""
import os
from pathlib import Path
from runtime_windows.task_store import TaskJournal, _directory
from runtime_windows.errors import PreparationError
from runtime_windows.source_identity import (_root, _check_chain, _check_stat, _identity,
                                            _cross_api_identity)
from .assets import read_bytes
from .contracts import (PARENT_FIELDS, Rejected, canonical, decode, digest, exact,
                        identifier, need, raw_sha, token, verify_record)

def exclusive(path, raw):
    need(type(raw) is bytes and len(raw) <= 1048576, "RECORD_BYTE_BUDGET", "RECORD")
    _check_chain(path, include_leaf=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(path), flags, 0o600)
    try:
        before = os.fstat(fd)
        _check_stat(before, False, "assessment_output")
        need(before.st_size == 0 and _cross_api_identity(path.lstat()) == _cross_api_identity(before),
             "ASSESSMENT_OUTPUT_IDENTITY", "RECORD")
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            need(written > 0, "PARTIAL_WRITE_PRESERVED", "RECORD")
            offset += written
        os.fsync(fd)
        after = os.fstat(fd)
        _check_stat(after, False, "assessment_output")
        path_after = path.lstat()
        _check_stat(path_after, False, "assessment_output_path")
        need((before.st_dev, before.st_ino, len(raw)) == (after.st_dev, after.st_ino, after.st_size) and
             before.st_mode == after.st_mode and before.st_nlink == after.st_nlink and
             _cross_api_identity(path_after) == _cross_api_identity(after),
             "ASSESSMENT_OUTPUT_CHANGED", "RECORD")
    finally:
        os.close(fd)
    need(read_bytes(path) == raw, "ASSESSMENT_OUTPUT_CHANGED", "RECORD")

def key_for(req):
    return digest(dict(task_id=req["task_ref"]["task_id"], request_id=req["request_id"]))

class RecordStore:
    def __init__(self, explicit_root, session, create=False):
        need(explicit_root is not None, "EXPLICIT_ASSESSMENT_ROOT_REQUIRED", "RECORD")
        token(session)
        need(session.startswith("oq_"), "INDEPENDENT_ASSESSMENT_SESSION_REQUIRED", "RECORD")
        self.parent = _root(Path(explicit_root))
        self.root = self.parent / session
        if not create:
            _directory(self.root)
        # Explicit root only. Never default PRIVATE_ROOT or TaskService events.
        self.journal = TaskJournal(session, root=self.parent)
        for name in ("claims", "artifacts"):
            _directory(self.root / name, create=create)
        self._events()

    def _events(self):
        events = self.journal.read()
        for event in events:
            need(event["kind"] == "ASSESSMENT_RECORDED", "FOREIGN_JOURNAL_EVENT", "RECORD")
            exact(event["payload"], ("idempotency_key", "request_digest", "assessment_id",
                "decision_id", "semantic_sha256", "artifact_sha256"), "ASSESSMENT_EVENT_SCHEMA")
        return events

    def _claim(self, key):
        return decode(read_bytes(self.root / "claims" / (key + ".json")))

    def _claim_snapshot(self, key):
        # One read attempt only. Private reservation bytes may still be in
        # their initial write; preserve the original guard code in the stop.
        try:
            return self._claim(key)
        except Rejected as exc:
            raise Rejected("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED:" + exc.code,
                           "RECORD") from exc
        except PreparationError as exc:
            if exc.code not in ("SOURCE_CHANGED_BEFORE_READ", "SOURCE_PATH_CHANGED_BEFORE_READ",
                                "SOURCE_CHANGED_DURING_READ", "SOURCE_PATH_CHANGED_AFTER_READ",
                                "SOURCE_READ_LENGTH_MISMATCH"):
                raise
            raise Rejected("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED:" + exc.code,
                           "RECORD") from exc

    def _commits(self, key):
        found = [e for e in self._events() if e["payload"]["idempotency_key"] == key]
        need(len(found) <= 1, "DUPLICATE_ASSESSMENT_COMMIT", "RECORD")
        return found

    def check_conflict(self, req):
        """Read-only early key check; no reservation or computation is created."""
        key = key_for(req)
        path = self.root / "claims" / (key + ".json")
        if path.exists() or path.is_symlink():
            previous = self._claim_snapshot(key)
            exact(previous, ("schema", "idempotency_key", "request_digest", "assessment_id"),
                  "ASSESSMENT_CLAIM_SCHEMA")
            need(previous["idempotency_key"] == key and
                 previous["request_digest"] == digest(req), "IDEMPOTENCY_CONFLICT", "RECORD")
            if not self._commits(key):
                raise Rejected("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED", "RECORD")
        else:
            need(not self._commits(key), "COMMITTED_CLAIM_MISSING", "RECORD")

    def reserve(self, req):
        key, material = key_for(req), digest(req)
        claim = dict(schema="H56_ASSESSMENT_CLAIM_V1", idempotency_key=key,
                     request_digest=material, assessment_id="ASSESS:" + material)
        path = self.root / "claims" / (key + ".json")
        committed = self._commits(key)
        if path.exists() or path.is_symlink():
            existing = self._claim_snapshot(key)
            exact(existing, claim, "ASSESSMENT_CLAIM_SCHEMA")
            need(existing == claim, "IDEMPOTENCY_CONFLICT", "RECORD")
            if committed:
                return claim, self.view_event(committed[0])
            raise Rejected("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED", "RECORD")
        need(not committed, "COMMITTED_CLAIM_MISSING", "RECORD")
        self.journal.require_capacity(1)
        try:
            exclusive(path, canonical(claim).encode("utf-8"))
        except FileExistsError:
            # A concurrent winner owns the reservation. Do not retry or compute.
            raise Rejected("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED", "RECORD") from None
        return claim, None

    def reference(self, event):
        payload = event["payload"]
        return dict(assessment_id=payload["assessment_id"], decision_id=payload["decision_id"],
                    semantic_sha256=payload["semantic_sha256"],
                    artifact_sha256=payload["artifact_sha256"], journal_event_sha256=event["event_sha256"])

    def view_event(self, event):
        payload = event["payload"]
        identifier(payload["assessment_id"], "ASSESS:")
        path = self.root / "artifacts" / (payload["assessment_id"][7:] + ".json")
        raw = read_bytes(path)
        need(raw_sha(raw) == payload["artifact_sha256"], "ASSESSMENT_ARTIFACT_DRIFT", "RECORD")
        record = verify_record(decode(raw, 1048576))
        need(all(record[k] == payload[k] for k in ("assessment_id", "decision_id", "semantic_sha256")),
             "ASSESSMENT_EVENT_BINDING_MISMATCH", "RECORD")
        return dict(record=record, reference=self.reference(event), integrity_checked=True,
                    native_recomputed=False, authority_granted=False, execution_permitted=False)

    def view(self, ref):
        exact(ref, PARENT_FIELDS, "ENV_PARENT_BINDING_MISMATCH")
        found = [e for e in self._events() if e["event_sha256"] == ref["journal_event_sha256"]]
        need(len(found) == 1 and self.reference(found[0]) == ref,
             "ENV_PARENT_BINDING_MISMATCH", "RECORD")
        return self.view_event(found[0])

    def commit(self, record, claim):
        verify_record(record)
        need(self._claim(claim["idempotency_key"]) == claim and
             record["assessment_id"] == claim["assessment_id"] and
             not self._commits(claim["idempotency_key"]), "ASSESSMENT_COMMIT_BINDING", "RECORD")
        self.journal.require_capacity(1)
        raw = canonical(record).encode("utf-8")
        path = self.root / "artifacts" / (record["assessment_id"][7:] + ".json")
        exclusive(path, raw)
        event = self.journal.append("ASSESSMENT_RECORDED", dict(
            idempotency_key=claim["idempotency_key"], request_digest=claim["request_digest"],
            assessment_id=record["assessment_id"], decision_id=record["decision_id"],
            semantic_sha256=record["semantic_sha256"], artifact_sha256=raw_sha(raw)))
        return self.view(self.reference(event))
