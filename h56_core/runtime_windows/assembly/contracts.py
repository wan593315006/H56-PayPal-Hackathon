"""Perimeter contracts. These are neither a fact ledger nor an authority service."""
from pathlib import Path
from dataclasses import dataclass
import hashlib
import json
import os

from ..paths import PRODUCT_ROOT, RUNTIME_ROOT, COMPONENT_ROOT, DATA_ROOT
ENGINEERING = DATA_ROOT
WORKSPACE = COMPONENT_ROOT
G0_COMMIT = '117d639885f041b9fceea4afd16d4f6d4e3ea80a'
CORE_COMMIT = '9221e16460258bc81e1176d69f63a09f81159b73'
C1_COMMIT = 'b01fa57f22c108e60ab26b1b285417d50f62b10c'
C1_MANIFEST = '9ed5f996152a4de096206a54f09e9d6b8b2866a5ef2593cd1a9c619ea2e0c723'


class AssemblyError(ValueError):
    def __init__(self, message, stage='ADMISSION'):
        super().__init__(message)
        self.stage = stage


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def raw_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise AssemblyError(label + '_EXACT_FIELDS_REQUIRED')


def strict_int(value, label):
    if type(value) is not int or value < 0:
        raise AssemblyError(label + '_NONNEGATIVE_STRICT_INTEGER_REQUIRED')
    return value


def safe_path(root, relative, must_exist=True):
    if type(relative) is not str or not relative or '\\' in relative or ':' in relative:
        raise AssemblyError('RELATIVE_LOCAL_PATH_REQUIRED')
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts) or relative.startswith('/'):
        raise AssemblyError('PATH_ESCAPE_REJECTED')
    current = root
    for part in (None, *parts):
        if part is not None:
            current = current / part
        if current.exists() or current.is_symlink():
            stat = current.lstat()
            if current.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                raise AssemblyError('LINK_OR_REPARSE_REJECTED')
            if current.is_file() and stat.st_nlink != 1:
                raise AssemblyError('SHARED_HARDLINK_REJECTED')
    current.resolve().relative_to(root.resolve())
    if must_exist and not current.is_file():
        raise AssemblyError('REGISTERED_FILE_MISSING:' + relative)
    return current


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise AssemblyError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_json(path):
    if path.stat().st_size > 12 * 1024 * 1024:
        raise AssemblyError('JSON_SIZE_BOUND')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(AssemblyError('NONFINITE_JSON')))


def schema_check(value, schema, label='DOCUMENT'):
    """The small exact subset used by the two checked-in schemas, no resolver."""
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    if 'type' in schema and type(value) is not types[schema['type']]:
        raise AssemblyError(label + '_SCHEMA_TYPE')
    if 'const' in schema and (type(value) is not type(schema['const']) or value != schema['const']):
        raise AssemblyError(label + '_SCHEMA_CONST')
    if 'enum' in schema and value not in schema['enum']:
        raise AssemblyError(label + '_SCHEMA_ENUM')
    if type(value) is dict:
        if not set(schema.get('required', [])).issubset(value):
            raise AssemblyError(label + '_SCHEMA_REQUIRED')
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - set(properties):
            raise AssemblyError(label + '_SCHEMA_UNKNOWN_FIELD')
        for key in value.keys() & properties.keys():
            schema_check(value[key], properties[key], label + '.' + key)
    if type(value) in (list, str):
        low = schema.get('minItems' if type(value) is list else 'minLength', 0)
        high = schema.get('maxItems' if type(value) is list else 'maxLength', 100000)
        if not low <= len(value) <= high:
            raise AssemblyError(label + '_SCHEMA_LENGTH')
    if type(value) is list and 'items' in schema:
        for item in value:
            schema_check(item, schema['items'], label + '[]')
    if type(value) is int and value < schema.get('minimum', value):
        raise AssemblyError(label + '_SCHEMA_MINIMUM')


def require_runtime(operation='candidate_compute'):
    """Explicit successor runtime approval; never the historical G2 release."""
    from ..runtime_admission import admit_runtime
    return admit_runtime(operation)


@dataclass(frozen=True)
class AssemblyPlan:
    domain_id: str
    scenario_id: str
    manifest_json: str
    assets_json: str
    input_json: str
    source_json: str

    def decoded(self):
        return tuple(json.loads(value) for value in
                     (self.manifest_json, self.assets_json, self.input_json, self.source_json))
