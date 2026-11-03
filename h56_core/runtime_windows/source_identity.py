"""Bounded byte-identity checks only; no native imports or import-time I/O.

The two-field public projection is not an approval, an external fact source,
or an execution grant.  The pinned commit is provenance metadata anchored by
the fixed vendor fingerprint; this module does not query Git or import it.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .errors import PreparationError


CORE_COMMIT = '9221e16460258bc81e1176d69f63a09f81159b73'
CONTRACT_SHA256 = '595a39bbca6319c701d5ccbcfcf7ea35d4568681a6f77c2648b998d3b4dde9c5'
VENDOR_FINGERPRINT = '6b2e942c7e542f874cee00a7930ad173c9856bcb4454699be6cc86fb55ea6b4b'
PRIVATE_LOCK_SHA256 = '7f7fadc4d731745cb02ef64855c87d7bbc0a174c84c29e592314584747d82287'
CORE_FILE_COUNT = 110
MAX_PUBLIC_LOCK_BYTES = 65536
MAX_PRIVATE_LOCK_BYTES = 8 * 1024 * 1024
MAX_VENDOR_BYTES = 1024 * 1024
MAX_VENDOR_ENTRIES = 512
MAX_PATH_LENGTH = 512
MAX_PATH_DEPTH = 16
MAX_FILE_BYTES = 512 * 1024
_HEX = re.compile(r'^[0-9a-f]{64}$')
_PART = re.compile(r'^[A-Za-z0-9_.-]+$')
_RESERVED = frozenset(['CON', 'PRN', 'AUX', 'NUL'] +
                      ['COM' + str(i) for i in range(1, 10)] +
                      ['LPT' + str(i) for i in range(1, 10)])


def _fail(code, detail=''):
    raise PreparationError(code, detail)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _duplicate_guard(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('DUPLICATE_JSON_KEY', key)
        result[key] = value
    return result


def _parse(raw, limit):
    if type(raw) is not bytes or len(raw) > limit:
        _fail('LOCK_BYTES_OR_BUDGET')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_duplicate_guard,
                          parse_constant=lambda value: _fail('NONFINITE_JSON', value))
    except PreparationError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        _fail('INVALID_LOCK_JSON', type(exc).__name__)


def parse_public_lock(raw):
    """Parse UTF-8 raw bytes, rejecting duplicate keys before dict conversion."""
    result = _parse(raw, MAX_PUBLIC_LOCK_BYTES)
    _validate_lock(result)
    return result


def _safe_name(name):
    if type(name) is not str or not name or len(name) > MAX_PATH_LENGTH:
        _fail('UNSAFE_VENDOR_PATH')
    parts = name.split('/')
    if len(parts) > MAX_PATH_DEPTH:
        _fail('UNSAFE_VENDOR_PATH', name)
    for part in parts:
        if (not _PART.fullmatch(part) or part in ('.', '..') or
                part.endswith('.') or part.split('.')[0].upper() in _RESERVED):
            _fail('UNSAFE_VENDOR_PATH', name)
    return parts


def _validate_lock(lock):
    if type(lock) is not dict or set(lock) != {'contract_sha256', 'vendor'}:
        _fail('PUBLIC_LOCK_EXACT_FIELDS')
    if lock['contract_sha256'] != CONTRACT_SHA256:
        _fail('ORIGINAL_CONTRACT_IDENTITY_MISMATCH')
    vendor = lock['vendor']
    if type(vendor) is not dict or len(vendor) != CORE_FILE_COUNT:
        _fail('CORE_CLOSURE_COUNT')
    folded, total = set(), 0
    for name, identity in vendor.items():
        _safe_name(name)
        if name.casefold() in folded:
            _fail('CASE_COLLIDING_VENDOR_PATH', name)
        folded.add(name.casefold())
        if type(identity) is not dict or set(identity) != {'sha256', 'size'}:
            _fail('VENDOR_IDENTITY_EXACT_FIELDS', name)
        size, digest = identity['size'], identity['sha256']
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
            _fail('FILE_SIZE_BUDGET', name)
        if type(digest) is not str or not _HEX.fullmatch(digest):
            _fail('INVALID_FILE_SHA256', name)
        total += size
    if total > MAX_VENDOR_BYTES:
        _fail('VENDOR_SIZE_BUDGET')
    if hashlib.sha256(_canonical(vendor)).hexdigest() != VENDOR_FINGERPRINT:
        _fail('CORE_FINGERPRINT_MISMATCH')
    return vendor


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, value.st_nlink,
            getattr(value, 'st_file_attributes', 0))


def _cross_api_identity(value):
    # Python 3.13 Windows lstat and fstat can expose different transitional
    # ctime semantics. Compare common object identity across APIs, then compare
    # full (including ctime) identities within each API before/after the read.
    # Windows path stat can derive 0111 execute bits from an .exe suffix while
    # descriptor stat omits them. Normalize only those bits for regular files
    # across APIs; file type/read-write bits and all same-API snapshots stay exact.
    mode = value.st_mode
    if os.name == 'nt' and stat.S_ISREG(mode):
        mode &= ~0o111
    return (value.st_dev, value.st_ino, mode, value.st_size,
            value.st_mtime_ns, value.st_nlink,
            getattr(value, 'st_file_attributes', 0),
            getattr(value, 'st_birthtime_ns', None))


def _check_stat(value, directory, label):
    if (stat.S_ISLNK(value.st_mode) or
            getattr(value, 'st_file_attributes', 0) & 0x400):
        _fail('LINK_OR_REPARSE_POINT', label)
    if directory:
        if not stat.S_ISDIR(value.st_mode):
            _fail('NOT_A_DIRECTORY', label)
    elif not stat.S_ISREG(value.st_mode):
        _fail('NOT_A_REGULAR_FILE', label)
    elif value.st_nlink != 1:
        _fail('HARDLINK_OR_UNKNOWN_LINK_COUNT', label)


def _check_chain(path, include_leaf=True):
    chain = list(reversed(path.parents)) + ([path] if include_leaf else [])
    for item in chain:
        _check_stat(item.lstat(), True, str(item))


def _root(component_root):
    if not isinstance(component_root, Path) or not component_root.is_absolute():
        _fail('ABSOLUTE_COMPONENT_ROOT_REQUIRED')
    if str(component_root).startswith(('\\\\', '//')):
        _fail('NETWORK_COMPONENT_ROOT_FORBIDDEN')
    if '..' in component_root.parts:
        _fail('ROOT_TRAVERSAL')
    _check_chain(component_root)
    return component_root


def _read_checked(path, expected_size, limit):
    """Check lstat/handle/path identity before bytes and after bounded reads."""
    _check_chain(path, include_leaf=False)
    before = path.lstat()
    _check_stat(before, False, str(path))
    if before.st_size > limit or (expected_size is not None and before.st_size != expected_size):
        _fail('SOURCE_SIZE_MISMATCH_OR_BUDGET', path.name)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        _check_stat(opened, False, str(path))
        if _cross_api_identity(opened) != _cross_api_identity(before):
            _fail('SOURCE_CHANGED_BEFORE_READ', path.name)
        _check_chain(path, include_leaf=False)
        if _identity(path.lstat()) != _identity(before):
            _fail('SOURCE_PATH_CHANGED_BEFORE_READ', path.name)
        chunks, count = [], 0
        while True:
            block = os.read(descriptor, min(65536, limit + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            if count > limit:
                _fail('SOURCE_READ_BUDGET', path.name)
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail('SOURCE_CHANGED_DURING_READ', path.name)
    finally:
        os.close(descriptor)
    _check_chain(path, include_leaf=False)
    if _identity(path.lstat()) != _identity(before):
        _fail('SOURCE_PATH_CHANGED_AFTER_READ', path.name)
    raw = b''.join(chunks)
    if len(raw) != before.st_size:
        _fail('SOURCE_READ_LENGTH_MISMATCH', path.name)
    return raw


def _snapshot(root):
    result, count, total = {}, 0, 0
    pending = [(root, '')]
    while pending:
        current, relative = pending.pop()
        value = current.lstat()
        _check_stat(value, True, relative or '.')
        result[relative] = ('directory', _identity(value))
        with os.scandir(str(current)) as entries:
            for entry in entries:
                count += 1
                if count > MAX_VENDOR_ENTRIES:
                    _fail('VENDOR_ENTRY_BUDGET')
                name = relative + '/' + entry.name if relative else entry.name
                _safe_name(name)
                # Windows DirEntry.stat may report inode/device/link-count as
                # zero. Use a fresh lstat, keeping the strict hardlink check.
                item = (current / entry.name).lstat()
                if stat.S_ISDIR(item.st_mode):
                    _check_stat(item, True, name)
                    pending.append((current / entry.name, name))
                else:
                    _check_stat(item, False, name)
                    if item.st_size > MAX_FILE_BYTES:
                        _fail('FILE_SIZE_BUDGET', name)
                    total += item.st_size
                    if total > MAX_VENDOR_BYTES:
                        _fail('VENDOR_SIZE_BUDGET')
                    result[name] = ('file', _identity(item))
    return result


def verify_public_lock(component_root, lock):
    """Verify only the local 110-file vendor; never read the private old lock.

    This is byte provenance verification, not OS access isolation. It cannot
    prevent an adversarial filesystem writer after this function returns.
    """
    vendor = _validate_lock(lock)
    try:
        root = _root(component_root) / 'engineering' / 'vendor'
        _check_chain(root)
        before = _snapshot(root)
        expected_directories = {''}
        for name in vendor:
            parts = name.split('/')
            expected_directories.update('/'.join(parts[:i]) for i in range(1, len(parts)))
        actual_files = {name for name, value in before.items() if value[0] == 'file'}
        actual_directories = {name for name, value in before.items() if value[0] == 'directory'}
        if actual_files != set(vendor) or actual_directories != expected_directories:
            _fail('EXTRA_OR_MISSING_NATIVE_SOURCE')
        for name in sorted(vendor):
            expected = vendor[name]
            raw = _read_checked(root.joinpath(*name.split('/')), expected['size'], MAX_FILE_BYTES)
            if hashlib.sha256(raw).hexdigest() != expected['sha256']:
                _fail('ORIGINAL_CORE_SOURCE_DRIFT', name)
        if _snapshot(root) != before:
            _fail('VENDOR_TREE_CHANGED_DURING_VERIFICATION')
    except PreparationError:
        raise
    except OSError as exc:
        _fail('SOURCE_FILESYSTEM_ERROR', type(exc).__name__)
    return {'status': 'SOURCE_IDENTITY_ONLY', 'source_commit': CORE_COMMIT,
            'contract_sha256': CONTRACT_SHA256,
            'vendor_fingerprint': VENDOR_FINGERPRINT, 'file_count': CORE_FILE_COUNT,
            'total_bytes': sum(item['size'] for item in vendor.values()),
            'external_fact_trust': False, 'execution_authority': False,
            'runtime_core_imported': False}


def build_public_lock(component_root):
    """Explicit private preparation only: project the anchored old lock."""
    try:
        root = _root(component_root)
        raw = _read_checked(root / 'offline' / 'source-lock.json', None, MAX_PRIVATE_LOCK_BYTES)
        if hashlib.sha256(raw).hexdigest() != PRIVATE_LOCK_SHA256:
            _fail('PRIVATE_LOCK_SOURCE_IDENTITY_MISMATCH')
        original = _parse(raw, MAX_PRIVATE_LOCK_BYTES)
        if type(original) is not dict or not {'contract_sha256', 'vendor'} <= set(original):
            _fail('PRIVATE_LOCK_REQUIRED_FIELDS')
        projection = {'contract_sha256': original['contract_sha256'], 'vendor': original['vendor']}
        verify_public_lock(root, projection)
        return projection
    except PreparationError:
        raise
    except OSError as exc:
        _fail('SOURCE_FILESYSTEM_ERROR', type(exc).__name__)
