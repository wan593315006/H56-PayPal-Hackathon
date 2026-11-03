"""Data boundary only. No authority producer or host collector."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from runtime_windows.assembly.contracts import canonical, digest

VERSION = "1.0.0"
GRADE = "SYNTHETIC_ONLY"
ROLE = "SIMULATED_OPERATOR_METADATA_HOST"
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
FIELDS = ("app_container", "integrity_rid", "outer_job_clear",
          "host_directory_normal", "dependencies_available", "supporting_attestation")
REQUEST_FIELDS = ("schema", "request_id", "task_ref", "environment_id",
                  "raw_evidence_sha256", "as_of", "source_manifest_sha256",
                  "asset_manifest_sha256", "interface_version", "parent_decision_ref")
TASK_FIELDS = ("task_id", "task_kind", "task_descriptor_sha256", "origin", "origin_record_ref")
PARENT_FIELDS = ("assessment_id", "decision_id", "semantic_sha256", "artifact_sha256",
                 "journal_event_sha256")
SEMANTIC_FIELDS = ("schema", "assessment_id", "parent_decision_ref", "task_ref",
    "environment_id", "evidence_grade", "raw_evidence_sha256", "source_validation",
    "source_binding", "asset_binding", "as_of", "fact_cores", "history", "snapshot",
    "version_tuple", "mapping_trace", "c1_catalog", "c1_definition", "c2_reference",
    "availability_assertion", "c2_context", "c2_projection", "admission_candidate",
    "reason_codes", "required_evidence", "boundary", "stage", "failure")
BOUNDARY = dict(candidate_planning_only=True, authority_granted=False,
                execution_permitted=False, formal_history_write=False, business_action_calls=0)
ALIASES = dict(FEASIBLE="ALLOW_CANDIDATE", INFEASIBLE="BLOCKED",
               DEFER="DEFER", NEED_MORE_EVIDENCE="NEED_MORE_EVIDENCE")
# Runtime process identities and paths belong in an external transport record.
FORBIDDEN_SEMANTIC_KEYS = frozenset(("pid", "run_id", "command", "exit_code",
    "python_version", "python_executable", "runtime_binding", "absolute_paths",
    "wall_clock_start", "wall_clock_end", "log_paths", "raw_error", "error_text"))

class Rejected(ValueError):
    def __init__(self, code, stage="INPUT"):
        super().__init__(code)
        self.code, self.stage = code, stage

def need(condition, code, stage="INPUT"):
    if not condition:
        raise Rejected(code, stage)

def exact(value, keys, code="ENV_INPUT_REJECTED"):
    need(type(value) is dict and set(value) == set(keys), code)
    return value

def token(value):
    need(type(value) is str and TOKEN.fullmatch(value) is not None, "ENV_INPUT_REJECTED")
    return value

def sha(value):
    need(type(value) is str and HEX.fullmatch(value) is not None, "ENV_SOURCE_OR_VERSION_MISMATCH")
    return value

def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()

def disjoint_roots(*values):
    roots = [Path(v) for v in values]
    return all(p.is_absolute() for p in roots) and all(
        a != b and a not in b.parents and b not in a.parents
        for index, a in enumerate(roots) for b in roots[index + 1:])

def _pairs(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, "ENV_EVIDENCE_CONFLICT")
        value[key] = item
    return value

def _bad_number(value):
    raise Rejected("ENV_INPUT_REJECTED")

def _bounded(value, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    need(depth <= 16 and count[0] <= 8192, "INPUT_DATA_BUDGET")
    if type(value) is dict:
        need(all(type(k) is str for k in value), "ENV_INPUT_REJECTED")
        for item in value.values():
            _bounded(item, depth + 1, count)
    elif type(value) is list:
        need(len(value) <= 1024, "INPUT_DATA_BUDGET")
        for item in value:
            _bounded(item, depth + 1, count)
    else:
        need(value is None or type(value) in (str, int, bool), "ENV_INPUT_REJECTED")
        if type(value) is str:
            need(len(value) <= 4096, "INPUT_DATA_BUDGET")
        if type(value) is int:
            need(abs(value) <= 2**63 - 1, "INPUT_DATA_BUDGET")

def decode(raw, maximum=262144):
    need(type(raw) is bytes and len(raw) <= maximum and not raw.startswith(b"\xef\xbb\xbf"),
         "INPUT_DATA_BUDGET")
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs,
                           parse_float=_bad_number, parse_constant=_bad_number)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected("ENV_INPUT_REJECTED") from None
    _bounded(value)
    return value

def stamp(value):
    need(type(value) is str and STAMP.fullmatch(value) is not None,
         "ENV_TIME_INVALID_OR_FUTURE")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise Rejected("ENV_TIME_INVALID_OR_FUTURE") from None
    return parsed

def task(value):
    exact(value, TASK_FIELDS, "ENV_TASK_SCOPE_MISMATCH")
    token(value["task_id"])
    sha(value["task_descriptor_sha256"])
    need(value["task_kind"] == "TASK:ENV_QUALIFICATION_ONLY" and
         value["origin"] == "SYNTHETIC_DEMO_TASK" and
         value["origin_record_ref"] == "SYNTHETIC_TASK_DESCRIPTOR_V1",
         "ENV_TASK_SCOPE_MISMATCH")
    need(value["task_descriptor_sha256"] == digest({k: value[k] for k in TASK_FIELDS
         if k != "task_descriptor_sha256"}), "ENV_TASK_SCOPE_MISMATCH")
    return value

def identifier(value, prefix):
    need(type(value) is str and value.startswith(prefix), "ENV_PARENT_BINDING_MISMATCH")
    sha(value[len(prefix):])
    return value

def request(value, enforce_version=True):
    exact(value, REQUEST_FIELDS)
    need(value["schema"] == "H56_OFFLINE_ASSESSMENT_REQUEST_V1" and
         type(value["interface_version"]) is str and len(value["interface_version"]) <= 64 and
         (not enforce_version or value["interface_version"] == VERSION),
         "ENV_SOURCE_OR_VERSION_MISMATCH")
    token(value["request_id"]); token(value["environment_id"]); task(value["task_ref"])
    for name in ("raw_evidence_sha256", "source_manifest_sha256", "asset_manifest_sha256"):
        sha(value[name])
    stamp(value["as_of"])
    parent = value["parent_decision_ref"]
    if parent is not None:
        exact(parent, PARENT_FIELDS, "ENV_PARENT_BINDING_MISMATCH")
        identifier(parent["assessment_id"], "ASSESS:")
        identifier(parent["decision_id"], "DECISION:")
        for key in PARENT_FIELDS[2:]:
            sha(parent[key])
    return value

def validate_boundary(value):
    exact(value, BOUNDARY, "CANDIDATE_BOUNDARY_VIOLATION")
    for k, v in BOUNDARY.items():
        need(type(value[k]) is type(v) and value[k] == v, "CANDIDATE_BOUNDARY_VIOLATION")

def semantic_guard(value):
    _bounded(value)
    def visit(item):
        if type(item) is dict:
            need(not (set(item) & FORBIDDEN_SEMANTIC_KEYS), "SEMANTIC_RUNTIME_FIELD")
            for key in ("authority_granted", "execution_permitted", "formal_history_write",
                        "external_fact_trust", "execution_authority"):
                if key in item:
                    need(item[key] is False, "CANDIDATE_BOUNDARY_VIOLATION")
            if "candidate_planning_only" in item:
                need(item["candidate_planning_only"] is True, "CANDIDATE_BOUNDARY_VIOLATION")
            if "business_action_calls" in item:
                need(type(item["business_action_calls"]) is int and item["business_action_calls"] == 0,
                     "CANDIDATE_BOUNDARY_VIOLATION")
            if "evidence_grade" in item:
                need(item["evidence_grade"] == GRADE, "ENV_SOURCE_GRADE_MISMATCH")
            for v in item.values():
                visit(v)
        elif type(item) is list:
            for v in item:
                visit(v)
        elif type(item) is str:
            need(item not in ("CURRENT_HOST", "REAL_HOST", "ACTUAL_RUNTIME_VERIFIED"),
                 "ENV_SOURCE_GRADE_MISMATCH")
            need(not item.startswith(("/", "\\\\")) and
                 re.match(r"^[A-Za-z]:[\\\\/]", item) is None, "SEMANTIC_ABSOLUTE_PATH")
    visit(value)

def seal(core):
    exact(core, SEMANTIC_FIELDS)
    validate_boundary(core["boundary"])
    need(core["evidence_grade"] == GRADE, "ENV_SOURCE_GRADE_MISMATCH")
    projection = core["c2_projection"]
    if projection is not None:
        need(projection["candidate_planning_only"] is True and
             projection["authority_granted"] is False and
             projection["execution_permitted"] is False, "CANDIDATE_BOUNDARY_VIOLATION")
        need(core["admission_candidate"] == ALIASES[projection["decision"]],
             "CANDIDATE_BOUNDARY_VIOLATION")
        need(projection["projection_hash"] == digest({k:v for k,v in projection.items()
              if k != "projection_hash"}) and
             projection["context_hash"] == core["c2_context"]["context_hash"] and
             projection["catalog_reference_hash"] == core["c2_reference"]["reference_hash"] and
             projection["availability_assertion_hash"] == core["availability_assertion"]["assertion_hash"],
             "NATIVE_RESULT_IDENTITY_MISMATCH")
    else:
        need(core["admission_candidate"] == "NO_DECISION", "CANDIDATE_BOUNDARY_VIOLATION")
    semantic_guard(core)
    result = dict(core)
    result["semantic_sha256"] = digest(core)
    result["decision_id"] = "DECISION:" + digest(dict(assessment_id=core["assessment_id"],
                                                    semantic_sha256=result["semantic_sha256"]))
    return result

def verify_record(record):
    exact(record, SEMANTIC_FIELDS + ("semantic_sha256", "decision_id"))
    core = {k: record[k] for k in SEMANTIC_FIELDS}
    need(seal(core) == record, "ASSESSMENT_RECORD_HASH_MISMATCH", "RECORD")
    return record
