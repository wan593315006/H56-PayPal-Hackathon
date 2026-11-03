"""Candidate perimeter for a future independently approved Windows host.

Import is inert. Externally supplied digest anchors are an operator/bootstrap
trust boundary, not a Human identity signature or a decision made by this code.
The present increment supplies no approved host, resources or preflight report.
Actual admission, native loading and subprocess calls must not run in source tests.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from .errors import PreparationError
from .paths import PRODUCT_ROOT, RUNTIME_ROOT, COMPONENT_ROOT, PRIVATE_ROOT
from .source_identity import _read_checked, _safe_name, parse_public_lock, verify_public_lock


ENV_NAMES = frozenset(('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'H56W_SESSION',
    'H56W_RELEASE_SHA256', 'H56W_SOURCE_SHA256', 'H56W_ENVIRONMENT_SHA256',
    'H56W_PREFLIGHT_SHA256', 'H56W_HOST_ACCEPTANCE_SHA256'))
OPERATIONS = frozenset(('candidate_compute', 'fresh_process_replay'))
PREFLIGHT_CHECKS = frozenset(('file_access_negative', 'credential_access_negative',
    'network_access_negative', 'child_escape_negative', 'resource_limit_negative',
    'read_only_source', 'profile_storage_scope'))
LINEAGE_FIELDS = ('runtime_source_manifest_sha256', 'runtime_contract_sha256',
                  'public_lock_sha256', 'original_component_manifest_sha256')
RELEASE_KEYS = frozenset(('schema', 'status', 'session_id', 'allowed_operations',
    *LINEAGE_FIELDS, 'environment_sha256', 'preflight_sha256', 'host_acceptance_sha256',
    'candidate_planning_only', 'authority_granted', 'execution_permitted',
    'formal_history_write', 'external_services'))
HEX = re.compile(r'[0-9a-f]{64}')
TOKEN = re.compile(r'[A-Za-z0-9_-]{1,64}')
CONTRACT_PATH = 'runtime_windows/WINDOWS_CONNECTION_CONTRACT.json'
SOURCE_PATH = 'runtime_windows/RUNTIME_SOURCE_MANIFEST.json'
LOCK_PATH = 'runtime_windows/public-source-lock.json'
ORIGINAL_MANIFEST = '28dc4c86addcc0de18bdfa5e1256a173080f205f65ffdca88ed1c3081bf86974'
RUNTIME_MODULES = (
    '__init__.py', 'errors.py', 'source_identity.py', 'kernel_probe.py', 'paths.py',
    'runtime_admission.py', 'launch_contract.py', 'launcher.py', 'win32_backend.py',
    'candidate_cli.py', 'assembly/__init__.py', 'assembly/contracts.py',
    'assembly/admission.py', 'assembly/loader.py', 'assembly/unit_admission.py',
    'assembly/pipeline.py', 'assembly/evidence.py', 'assembly/replay.py',
    'adapters/__init__.py', 'adapters/bounded_rules.py', 'adapters/core_context.py',
    'host_contract.py', 'host_authority.py', 'host_resources.py', 'candidate_host.py',
    'task_catalog.py', 'task_store.py', 'tasks.py', 'task_cli.py',
)
DATA_CONTRACTS = ('assembly_lock.json', 'domain_manifest.schema.json',
    'input_bundle.schema.json', 'money_unit_admission.json', 'money_unit_admission.schema.json')


def refuse(code):
    raise PreparationError(code)


def _exact(value, fields, code):
    if type(value) is not dict or set(value) != set(fields):
        refuse(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), allow_nan=False).encode('utf-8'))


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            refuse('WIN_DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def decode(raw):
    if type(raw) is not bytes or len(raw) > 1048576:
        refuse('WIN_JSON_BUDGET')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_float=lambda _: refuse('WIN_NONINTEGER_NUMBER'),
                          parse_constant=lambda _: refuse('WIN_NONFINITE_NUMBER'))
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, PreparationError):
            raise
        refuse('WIN_INVALID_JSON')


def _relative(name):
    if (type(name) is not str or not name or len(name) > 512 or
            '\\' in name or ':' in name or name.startswith('/') or
            any(part in ('', '.', '..') for part in name.split('/'))):
        refuse('WIN_REGISTERED_RELATIVE_PATH_REQUIRED')
    _safe_name(name)
    return name.split('/')


def _bytes(root, name, maximum=1048576):
    path = root.joinpath(*_relative(name))
    return _read_checked(path, None, maximum)


def checked_environment_pins(environ):
    """Exact names, required variables and digest values are separate checks."""
    _exact(environ, ENV_NAMES, 'WIN_ENV_NAMES_NOT_EXACT')
    if any(type(value) is not str or not value or '\x00' in value for value in environ.values()):
        refuse('WIN_ENV_VALUES_INVALID')
    if TOKEN.fullmatch(environ['H56W_SESSION']) is None:
        refuse('WIN_SESSION_ID_INVALID')
    for name in ENV_NAMES - {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'H56W_SESSION'}:
        if HEX.fullmatch(environ[name]) is None:
            refuse('WIN_EXTERNAL_DIGEST_UNBOUND')
    return dict(environ)


def operation_closure(operation, allowed):
    if type(operation) is not str or operation not in OPERATIONS or type(allowed) is not list or not allowed:
        refuse('WIN_OPERATION_INVALID')
    if any(type(item) is not str for item in allowed) or len(set(allowed)) != len(allowed) or not set(allowed) <= OPERATIONS:
        refuse('WIN_OPERATION_INVALID')
    needed = {operation} | ({'candidate_compute'} if operation == 'fresh_process_replay' else set())
    if not needed <= set(allowed):
        refuse('WIN_OPERATION_NOT_GRANTED')


def validate_release(release, operation, pins, identities):
    """Structural/binding validation only, not authentication of a Human."""
    _exact(release, RELEASE_KEYS, 'WIN_RELEASE_FIELDS')
    if release['schema'] != 'h56.windows-runtime-release.v2' or release['status'] != 'EXTERNALLY_APPROVED_CANDIDATE_ONLY':
        refuse('WIN_SEPARATE_RUNTIME_RELEASE_REQUIRED')
    if release['session_id'] != pins['H56W_SESSION']:
        refuse('WIN_SESSION_BINDING_MISMATCH')
    operation_closure(operation, release['allowed_operations'])
    if release['candidate_planning_only'] is not True or any(release[key] is not False for key in ('authority_granted', 'execution_permitted', 'formal_history_write', 'external_services')):
        refuse('WIN_AUTHORITY_BOUNDARY_DRIFT')
    for key in LINEAGE_FIELDS:
        if release[key] != identities[key]:
            refuse('WIN_RELEASE_SOURCE_BINDING_MISMATCH')
    for field, name in (('environment_sha256', 'H56W_ENVIRONMENT_SHA256'), ('preflight_sha256', 'H56W_PREFLIGHT_SHA256'),
                        ('host_acceptance_sha256', 'H56W_HOST_ACCEPTANCE_SHA256')):
        if release[field] != pins[name]:
            refuse('WIN_RELEASE_CONTROL_BINDING_MISMATCH')


def validate_worker_documents(release, environment, preflight, acceptance,
                              operation, pins, identities, roots):
    """Shared pure schema/binding checks; not Human authentication or OS proof.

    The concrete host additionally pins original Human text and the seven-file
    bundle, verifies their resource/evidence closure and performs live readback.
    A worker receives only the exact, trusted-host-supplied environment anchors.
    """
    checked_environment_pins(pins)
    _exact(roots, ('control_root', 'scratch_root', 'receipt_input_root'), 'WIN_ROOT_FIELDS')
    validate_release(release, operation, pins, identities)
    _exact(environment, ('schema', 'session_id', 'python_executable', 'python_sha256',
        'variables', 'observation_policy', 'runtime_read_roots', 'profile_storage_root',
        'resource_contract_sha256', 'scratch_root', 'control_root', 'receipt_input_root'),
        'WIN_ENVIRONMENT_FIELDS')
    if environment['schema'] != 'h56.windows-runtime-environment.v2' or environment['session_id'] != pins['H56W_SESSION']:
        refuse('WIN_ENVIRONMENT_IDENTITY')
    for name in roots:
        if type(roots[name]) is not str or not roots[name] or environment[name] != roots[name]:
            refuse('WIN_PRIVATE_ROOT_BINDING_MISMATCH')
    if len(set(roots.values())) != 3:
        refuse('WIN_RECEIPT_INPUT_NOT_SEPARATE')
    expected = environment['variables']
    _exact(expected, ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'), 'WIN_ENVIRONMENT_VALUE_FIELDS')
    if any(type(value) is not str or not value or pins[name] != value for name, value in expected.items()):
        refuse('WIN_ENVIRONMENT_VALUE_MISMATCH')
    if pins['TEMP'] != roots['scratch_root'] or pins['TMP'] != roots['scratch_root']:
        refuse('WIN_TEMP_OUTSIDE_PRIVATE_SCRATCH')
    resource = environment['resource_contract_sha256']
    if type(resource) is not str or HEX.fullmatch(resource) is None:
        refuse('WIN_RESOURCE_CONTRACT_UNBOUND')
    _exact(preflight, ('schema', 'status', 'environment_sha256', 'runtime_source_manifest_sha256',
        'resource_contract_sha256', 'required_checks', 'preflight_evidence_index_sha256'), 'WIN_PREFLIGHT_FIELDS')
    if preflight['schema'] != 'h56.windows-controller-preflight-record.v2' or preflight['status'] != 'EXTERNALLY_ACCEPTED_RECORD':
        refuse('WIN_ISOLATION_PREFLIGHT_NOT_ACCEPTED')
    _exact(preflight['required_checks'], PREFLIGHT_CHECKS, 'WIN_PREFLIGHT_CHECK_SET')
    if any(value != 'VERIFIED' for value in preflight['required_checks'].values()):
        refuse('WIN_ISOLATION_PREFLIGHT_INCOMPLETE')
    if (preflight['environment_sha256'] != pins['H56W_ENVIRONMENT_SHA256'] or
            preflight['runtime_source_manifest_sha256'] != identities['runtime_source_manifest_sha256'] or
            preflight['resource_contract_sha256'] != resource):
        refuse('WIN_PREFLIGHT_BINDING_MISMATCH')
    if type(preflight['preflight_evidence_index_sha256']) is not str or HEX.fullmatch(preflight['preflight_evidence_index_sha256']) is None:
        refuse('WIN_PREFLIGHT_EVIDENCE_UNBOUND')
    _exact(acceptance, ('schema', 'status', 'session_id', 'runtime_source_manifest_sha256',
        'runtime_contract_sha256', 'public_lock_sha256', 'resource_contract_sha256',
        'preflight_sha256', 'allowed_operations', 'domain_scenarios', 'worker_attempt_budget',
        'candidate_planning_only', 'authority_granted', 'execution_permitted',
        'formal_history_write', 'external_services'), 'WIN_HOST_ACCEPTANCE_FIELDS')
    if acceptance['schema'] != 'h56.windows-host-acceptance.v1' or acceptance['status'] != 'EXTERNALLY_ACCEPTED_CANDIDATE_HOST':
        refuse('WIN_SEPARATE_HOST_ACCEPTANCE_REQUIRED')
    if acceptance['session_id'] != pins['H56W_SESSION']:
        refuse('WIN_HOST_SESSION_BINDING_MISMATCH')
    for key in ('runtime_source_manifest_sha256', 'runtime_contract_sha256', 'public_lock_sha256'):
        if acceptance[key] != identities[key]:
            refuse('WIN_HOST_SOURCE_BINDING_MISMATCH')
    if acceptance['resource_contract_sha256'] != resource or acceptance['preflight_sha256'] != pins['H56W_PREFLIGHT_SHA256']:
        refuse('WIN_HOST_RESOURCE_BINDING_MISMATCH')
    operation_closure(operation, acceptance['allowed_operations'])
    if set(acceptance['allowed_operations']) != set(release['allowed_operations']):
        refuse('WIN_HOST_OPERATION_BINDING_MISMATCH')
    if acceptance['candidate_planning_only'] is not True or any(acceptance[key] is not False for key in ('authority_granted', 'execution_permitted', 'formal_history_write', 'external_services')):
        refuse('WIN_HOST_AUTHORITY_BOUNDARY_DRIFT')
    domains = acceptance['domain_scenarios']
    if type(domains) is not dict or not domains or not set(domains) <= {'DEVSECOPS', 'FINANCE_REFUND'}:
        refuse('WIN_HOST_DOMAIN_SCOPE_INVALID')
    for scenarios in domains.values():
        if (type(scenarios) is not list or not 1 <= len(scenarios) <= 64 or
                any(type(name) is not str or TOKEN.fullmatch(name) is None for name in scenarios) or
                len(set(scenarios)) != len(scenarios)):
            refuse('WIN_HOST_SCENARIO_SCOPE_INVALID')
    if type(acceptance['worker_attempt_budget']) is not int or not 1 <= acceptance['worker_attempt_budget'] <= 100:
        refuse('WIN_HOST_ATTEMPT_BUDGET_INVALID')


def check_domain_scope(decision, domain_id, scenario_id):
    """A host's allowed task scope never expands because the asset exists."""
    domains = decision.get('allowed_domain_scenarios')
    if (type(domain_id) is not str or type(scenario_id) is not str or
            type(domains) is not dict or domain_id not in domains or scenario_id not in domains[domain_id]):
        refuse('WIN_DOMAIN_SCENARIO_NOT_GRANTED')


def verify_current_sources(manifest):
    _exact(manifest, ('schema', 'files', 'member_count'), 'WIN_RUNTIME_SOURCE_FIELDS')
    members = manifest['files']
    if manifest['schema'] != 'h56.windows-effective-source.v1' or type(members) is not list or not 1 <= len(members) <= 256 or type(manifest['member_count']) is not int or manifest['member_count'] != len(members):
        refuse('WIN_RUNTIME_SOURCE_COUNT')
    registry, folded, total = {}, set(), 0
    for member in members:
        _exact(member, ('path', 'size', 'sha256'), 'WIN_SOURCE_MEMBER_FIELDS')
        name = member['path']
        _relative(name)
        if name == SOURCE_PATH or name.casefold() in folded or '/.local/' in '/' + name + '/':
            refuse('WIN_SOURCE_MEMBER_DUPLICATE_OR_PRIVATE')
        if type(member['size']) is not int or not 0 <= member['size'] <= 1048576 or type(member['sha256']) is not str or HEX.fullmatch(member['sha256']) is None:
            refuse('WIN_SOURCE_MEMBER_IDENTITY')
        raw = _bytes(PRODUCT_ROOT, name)
        if len(raw) != member['size'] or _sha(raw) != member['sha256']:
            refuse('WIN_CURRENT_SOURCE_DRIFT')
        total += len(raw)
        if total > 8388608:
            refuse('WIN_SOURCE_TREE_BUDGET')
        folded.add(name.casefold())
        registry[name] = {'sha256': member['sha256'], 'size': member['size']}
    return registry


def required_runtime_paths(public_lock):
    """Complete declared source/data closure, not the whole private archive."""
    parse_public_lock(json.dumps(public_lock, separators=(',', ':')).encode('utf-8'))
    component = 'runtime_binding_v1_20261024/engineering/'
    names = {'runtime_windows/' + name for name in RUNTIME_MODULES}
    names.update((CONTRACT_PATH, LOCK_PATH))
    names.update(component + 'contracts/' + name for name in DATA_CONTRACTS)
    names.update(component + 'assets/' + domain + '/' + name
                 for domain in ('devsecops', 'finance_refund')
                 for name in ('domain_assets.json', 'inputs.json', 'manifest.json'))
    names.update(component + 'vendor/' + name for name in public_lock['vendor'])
    return names


def _directory(path):
    for item in list(reversed(path.parents)) + [path]:
        value = item.lstat()
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
            refuse('WIN_PRIVATE_DIRECTORY_UNSAFE')


def admit_runtime(operation='candidate_compute'):
    """Worker-only admission after an externally anchored trusted-host launch.

    Source readiness never replaces host acceptance. The same-user trusted
    operator is the bootstrap boundary, not cryptographic Human authentication.
    This entry cannot provision resources, authorize actions or spawn a child.
    """
    if os.name != 'nt' or not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode or sys.flags.utf8_mode != 1:
        refuse('WIN_APPROVED_ISOLATED_PYTHON_REQUIRED')
    pins = checked_environment_pins(dict(os.environ))
    base = PRIVATE_ROOT / pins['H56W_SESSION']
    control, scratch, receipt_input = base / 'control', base / 'scratch', base / 'replay_input'
    for directory in (control, scratch, scratch / 'runs', scratch / 'child_failures', receipt_input):
        _directory(directory)
    filenames = {'release': ('release.json', 'H56W_RELEASE_SHA256'),
        'environment': ('environment.json', 'H56W_ENVIRONMENT_SHA256'),
        'preflight': ('preflight.json', 'H56W_PREFLIGHT_SHA256'),
        'acceptance': ('host_acceptance.json', 'H56W_HOST_ACCEPTANCE_SHA256')}
    documents = {}
    for label, (filename, pin) in filenames.items():
        raw = _bytes(control, filename)
        if _sha(raw) != pins[pin]:
            refuse('WIN_EXTERNAL_CONTROL_ANCHOR_MISMATCH')
        documents[label] = decode(raw)
    manifest_raw = _bytes(PRODUCT_ROOT, SOURCE_PATH)
    if _sha(manifest_raw) != pins['H56W_SOURCE_SHA256']:
        refuse('WIN_RUNTIME_MANIFEST_ANCHOR_MISMATCH')
    registry = verify_current_sources(decode(manifest_raw))
    contract_raw, lock_raw = _bytes(PRODUCT_ROOT, CONTRACT_PATH), _bytes(PRODUCT_ROOT, LOCK_PATH)
    contract, public_lock = decode(contract_raw), parse_public_lock(lock_raw)
    if contract.get('schema') != 'h56.windows-candidate-connection.v2' or contract.get('boundary') != {
            'candidate_planning_only': True, 'authority_granted': False,
            'execution_permitted': False, 'formal_history_write': False, 'external_services': False}:
        refuse('WIN_RUNTIME_CONTRACT_BOUNDARY')
    if contract.get('launch_status') != 'PREPARED_NOT_RUNTIME_ACCEPTED':
        refuse('WIN_SOURCE_PREPARATION_STATE_INVALID')
    if set(registry) != required_runtime_paths(public_lock):
        refuse('WIN_EFFECTIVE_SOURCE_CLOSURE_MISMATCH')
    verify_public_lock(COMPONENT_ROOT, public_lock)
    identities = dict(runtime_source_manifest_sha256=_sha(manifest_raw),
        runtime_contract_sha256=_sha(contract_raw), public_lock_sha256=_sha(lock_raw),
        original_component_manifest_sha256=ORIGINAL_MANIFEST)
    roots = dict(control_root=str(control), scratch_root=str(scratch), receipt_input_root=str(receipt_input))
    environment, preflight = documents['environment'], documents['preflight']
    validate_worker_documents(documents['release'], environment, preflight,
        documents['acceptance'], operation, pins, identities, roots)
    if _sha(_bytes(control, 'resource_contract.json')) != environment['resource_contract_sha256']:
        refuse('WIN_RESOURCE_CONTRACT_ANCHOR_MISMATCH')
    if _sha(_bytes(control, 'preflight_evidence_index.json')) != preflight['preflight_evidence_index_sha256']:
        refuse('WIN_PREFLIGHT_EVIDENCE_ANCHOR_MISMATCH')
    python = Path(environment['python_executable'])
    if (not python.is_absolute() or str(python).startswith(('\\\\', '//')) or python != Path(sys.executable) or
            type(environment['python_sha256']) is not str or HEX.fullmatch(environment['python_sha256']) is None or
            _sha(_read_checked(python, None, 2097152)) != environment['python_sha256']):
        refuse('WIN_CURRENT_PYTHON_IDENTITY')
    if (type(environment['runtime_read_roots']) is not list or not environment['runtime_read_roots'] or
            any(type(path) is not str or not Path(path).is_absolute() for path in environment['runtime_read_roots']) or
            type(environment['profile_storage_root']) is not str or not Path(environment['profile_storage_root']).is_absolute()):
        refuse('WIN_PROFILE_OR_RUNTIME_CLOSURE_UNBOUND')
    # Live token/Job readback is necessary; it is not evidence of effective
    # network/file/credential denial. Those remain externally accepted tests.
    from .kernel_probe import collect_current_process_observation, evaluate_observation
    observation = collect_current_process_observation(environment['observation_policy'])
    comparison = evaluate_observation(environment['observation_policy'], observation)
    if comparison['status'] != 'OBSERVED_MATCH_NEGATIVE_TESTS_PENDING':
        refuse('WIN_CURRENT_PROCESS_BOUNDARY_MISMATCH')
    return dict(identities, verified_source_registry=registry,
        release_sha256=pins['H56W_RELEASE_SHA256'],
        environment_sha256=pins['H56W_ENVIRONMENT_SHA256'],
        preflight_sha256=pins['H56W_PREFLIGHT_SHA256'],
        host_acceptance_sha256=pins['H56W_HOST_ACCEPTANCE_SHA256'],
        allowed_domain_scenarios=documents['acceptance']['domain_scenarios'],
        child_environment=pins, live_observation=observation, live_comparison=comparison,
        trust_scope='EXTERNALLY_PINNED_OPERATOR_INPUTS_NOT_CRYPTOGRAPHIC_HUMAN_IDENTITY',
        authority_granted=False, execution_permitted=False, **roots)


def child_environment(decision):
    """Compatibility data accessor; it does not permit a worker launch."""
    return checked_environment_pins(decision['child_environment'])


def run_bounded(argv, env):
    """Retired nested-worker entry; the trusted host owns every fresh Job."""
    refuse('HOST_FRESH_PROCESS_REQUIRED')
