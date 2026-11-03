"""Private task observations; checksum chains are not execution attestations."""
import os
from pathlib import Path
import re
import stat

from .assembly.contracts import canonical, digest
from .paths import PRIVATE_ROOT
from .runtime_admission import decode
from .source_identity import _read_checked, _identity, _cross_api_identity, _check_stat

TOKEN = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
MAX_EVENTS = 512
MAX_BYTES = 1048576
MAX_EVENT_BYTES = 65536
SCOPE = 'PRIVATE_TASK_CONTROL_NOT_FACT_STATE_OR_AUTHORITY'


class TaskStoreError(ValueError):
    pass


def _directory(path, create=False):
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or '..' in path.parts:
        raise TaskStoreError('PRIVATE_LOCAL_ABSOLUTE_DIRECTORY_REQUIRED')
    for item in list(reversed(path.parents)) + [path]:
        if not item.exists() and not item.is_symlink():
            if not create:
                raise TaskStoreError('PRIVATE_DIRECTORY_MISSING')
            item.mkdir()
        value = item.lstat()
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
            raise TaskStoreError('PRIVATE_DIRECTORY_LINK_OR_TYPE')


class TaskJournal:
    def __init__(self, session, root=None):
        if type(session) is not str or TOKEN.fullmatch(session) is None:
            raise TaskStoreError('INVALID_PRIVATE_SESSION_ID')
        parent = PRIVATE_ROOT / 'tasks' if root is None else Path(root)
        _directory(parent, create=True)
        self.root = parent / session
        _directory(self.root, create=True)
        self.session = session
        self.path = self.root / 'events.jsonl'
        self.lock = self.root / 'writer.lock'
        self.events = self.read()

    def read(self):
        _directory(self.root)
        if not self.path.exists() and not self.path.is_symlink():
            return []
        raw = _read_checked(self.path, None, MAX_BYTES)
        if raw and not raw.endswith(b'\n'):
            raise TaskStoreError('PARTIAL_EVENT_PRESERVED_NO_AUTOREPAIR')
        lines = raw.splitlines()
        if len(lines) > MAX_EVENTS:
            raise TaskStoreError('EVENT_BUDGET_EXCEEDED')
        events, previous = [], '0' * 64
        for sequence, line in enumerate(lines, 1):
            event = decode(line)
            if type(event) is not dict or set(event) != {'sequence', 'previous', 'kind', 'payload', 'event_sha256'}:
                raise TaskStoreError('EVENT_SCHEMA_DRIFT')
            if type(event['kind']) is not str or type(event['payload']) is not dict:
                raise TaskStoreError('EVENT_SCHEMA_DRIFT')
            core = {key: value for key, value in event.items() if key != 'event_sha256'}
            if type(event['sequence']) is not int or event['sequence'] != sequence or event['previous'] != previous or digest(core) != event['event_sha256']:
                raise TaskStoreError('EVENT_CHAIN_INTEGRITY_FAILURE')
            previous = event['event_sha256']
            events.append(event)
        return events

    def require_capacity(self, slots=1):
        if type(slots) is not int or slots < 1 or len(self.events) + slots > MAX_EVENTS:
            raise TaskStoreError('EVENT_BUDGET_EXCEEDED')
        # Reserve finite metadata space before any Host call. This is an
        # application budget, not an OS disk quota or resource guarantee.
        used = sum(len(canonical(event).encode('utf-8')) + 1 for event in self.events)
        if used + slots * MAX_EVENT_BYTES > MAX_BYTES:
            raise TaskStoreError('EVENT_BYTE_RESERVATION_EXCEEDED')

    def append(self, kind, payload):
        self.require_capacity()
        _directory(self.root)
        descriptor = os.open(str(self.lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            lock_identity = os.fstat(descriptor)
            _check_stat(lock_identity, False, 'task_writer_lock')
            os.write(descriptor, b'Private single writer; no automatic stale lock removal.\n')
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            if self.read() != self.events:
                raise TaskStoreError('CONCURRENT_WRITER_RELOAD_REQUIRED')
            event = {'sequence': len(self.events) + 1,
                     'previous': self.events[-1]['event_sha256'] if self.events else '0' * 64,
                     'kind': kind, 'payload': decode(canonical(payload).encode('utf-8'))}
            event['event_sha256'] = digest(event)
            raw = (canonical(event) + '\n').encode('utf-8')
            if len(raw) > MAX_EVENT_BYTES:
                raise TaskStoreError('EVENT_BYTE_BUDGET_EXCEEDED')
            existed = self.path.exists() or self.path.is_symlink()
            before = self.path.lstat() if existed else None
            if existed:
                previous_raw = _read_checked(self.path, None, MAX_BYTES)
                expected_raw = ''.join(canonical(value) + '\n' for value in self.events).encode('utf-8')
                if previous_raw != expected_raw or _identity(self.path.lstat()) != _identity(before):
                    raise TaskStoreError('TASK_LOG_CHANGED_BEFORE_APPEND')
            flags = os.O_WRONLY | os.O_APPEND | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            if not existed:
                flags |= os.O_CREAT | os.O_EXCL
            output = os.open(str(self.path), flags, 0o600)
            try:
                opened = os.fstat(output)
                _check_stat(opened, False, 'task_event_output')
                if existed and _cross_api_identity(opened) != _cross_api_identity(before):
                    raise TaskStoreError('TASK_LOG_OPENED_IDENTITY_DRIFT')
                if not existed and opened.st_size != 0:
                    raise TaskStoreError('TASK_LOG_NEW_FILE_NOT_EMPTY')
                _directory(self.root)
                if _cross_api_identity(self.path.lstat()) != _cross_api_identity(opened):
                    raise TaskStoreError('TASK_LOG_PATH_HANDLE_MISMATCH')
                # Recheck the opened object's links immediately before writes.
                _check_stat(os.fstat(output), False, 'task_event_output')
                written = 0
                while written < len(raw):
                    count = os.write(output, raw[written:])
                    if count <= 0:
                        raise TaskStoreError('TASK_LOG_PARTIAL_APPEND')
                    written += count
                os.fsync(output)
                after = os.fstat(output)
                _check_stat(after, False, 'task_event_output')
                if (after.st_dev, after.st_ino, after.st_size) != (opened.st_dev, opened.st_ino, opened.st_size + len(raw)):
                    raise TaskStoreError('TASK_LOG_APPEND_IDENTITY_OR_SIZE_DRIFT')
                if _cross_api_identity(self.path.lstat()) != _cross_api_identity(after):
                    raise TaskStoreError('TASK_LOG_PATH_CHANGED_AFTER_APPEND')
            finally:
                os.close(output)
            self.events.append(event)
            return event
        finally:
            # Do not remove a different writer's replacement or a linked path.
            lock_path = self.lock.lstat()
            _check_stat(lock_path, False, 'task_writer_lock')
            if (lock_path.st_dev, lock_path.st_ino) != (lock_identity.st_dev, lock_identity.st_ino):
                raise TaskStoreError('TASK_WRITER_LOCK_IDENTITY_DRIFT')
            self.lock.unlink()
