"""Assemble the ten-key request, call the kernel, and keep the bytes that prove it.

This is the only module in `app/` allowed to import the kernel, and it does so inside
functions. `selfcheck` and `--help` must not pay for 110 vendor files they never touch.

Three details are easy to get wrong and are handled here once:

* `task_descriptor_sha256` is `digest()` over the other four `task_ref` keys. Hand-filling
  it, or using `sha256(json.dumps(...))`, produces `ENV_TASK_SCOPE_MISMATCH` and looks like
  a scope bug in the kernel.
* the record root must exist *before* `RecordStore` is constructed: it walks the whole path
  with `lstat()` and refuses a missing root, and `create=True` only makes the two
  subdirectories underneath. So `open_store()` creates the root itself.
* `raw_evidence_sha256` is taken over the bytes written to `evidence.json`. A digest over a
  dict is a different number, and it fails later as `ENV_INPUT_HASH_MISMATCH`.
"""
import sys
from pathlib import Path

from . import hostproof, settings

SCHEMA = "H56_OFFLINE_ASSESSMENT_REQUEST_V1"
INTERFACE_VERSION = "1.0.0"
TASK_KIND = "TASK:ENV_QUALIFICATION_ONLY"
TASK_ORIGIN = "SYNTHETIC_DEMO_TASK"
TASK_ORIGIN_REF = "SYNTHETIC_TASK_DESCRIPTOR_V1"

RUN_FILES = ("request.json", "evidence.json", "result.json")


class BridgeError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def kernel():
    """Import the kernel from the package's own copy, never from the working directory."""
    root = str(settings.CORE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from offline_qualification_v1 import assessment, contracts, records
    return contracts, records, assessment


def task_ref(task_id):
    """Five keys, with the descriptor digest derived from the other four."""
    contracts = kernel()[0]
    body = dict(task_id=task_id, task_kind=TASK_KIND,
                origin=TASK_ORIGIN, origin_record_ref=TASK_ORIGIN_REF)
    return dict(body, task_descriptor_sha256=contracts.digest(body))


def request_document(request_id, task, environment_id, raw_evidence_sha256, as_of,
                     parent_decision_ref=None):
    return {
        "schema": SCHEMA,
        "request_id": request_id,
        "task_ref": task,
        "environment_id": environment_id,
        "raw_evidence_sha256": raw_evidence_sha256,
        "as_of": as_of,
        "source_manifest_sha256": settings.SOURCE_MANIFEST_SHA,
        "asset_manifest_sha256": settings.ASSET_MANIFEST_SHA,
        "interface_version": INTERFACE_VERSION,
        "parent_decision_ref": parent_decision_ref,
    }


def identifiers(business, stamp):
    """Token-shaped names for one run. No colon, slash, space or non-ASCII survives here."""
    return dict(
        request_id="req_%s_%s" % (business, stamp),
        environment_id="ENV-%s-%s" % (business, stamp),
        task_id="TASK-%s-%s" % (business, stamp),
        session="oq_%s_%s" % (business, stamp),
    )


def open_store(records_root, session):
    """Create the record root if needed, then open the store. Root first, always."""
    records = kernel()[1]
    root = Path(records_root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    return records.RecordStore(root, session, create=True)


def check_canonical(value):
    """One assertion that our serialiser and the kernel's agree, on real payload bytes."""
    canonical = kernel()[0].canonical
    mine, theirs = hostproof.dumps(value), canonical(value)
    if mine != theirs:
        raise BridgeError("CANONICAL_DRIFT", "app.hostproof.dumps != kernel canonical")
    return theirs


def evaluate(envelope_raw, request, records_root, session):
    """Run one assessment and return the kernel's result envelope."""
    contracts, _records, assessment = kernel()
    if hostproof.dumps(request) != contracts.canonical(request):
        raise BridgeError("CANONICAL_DRIFT")
    store = open_store(records_root, session)
    return assessment.evaluate(envelope_raw, request, store)


def write_run(run_directory, request, envelope_raw, result):
    """Persist the three documents of a run; bytes are canonical so a digest recomputes."""
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=True)
    documents = {
        "request.json": request,
        "result.json": result,
    }
    for name, value in documents.items():
        (directory / name).write_bytes(hostproof.dumps(value).encode("utf-8"))
    (directory / "evidence.json").write_bytes(envelope_raw)
    return directory


def summarize(result):
    """The few numbers worth printing. No environment values, no absolute paths."""
    record = result["record"]
    projection = record.get("c2_projection") or {}
    calls = (record.get("mapping_trace") or {}).get("native_calls") or []
    returned = sum(1 for call in calls if call.get("status") == "RETURNED")
    return {
        "decision": projection.get("decision", "NO_DECISION"),
        "reason_codes": list(record.get("reason_codes") or []),
        "stage": record.get("stage"),
        "assessment_id": record.get("assessment_id"),
        "decision_id": record.get("decision_id"),
        "native_calls": len(calls),
        "native_returned": returned,
        "evidence_state": (record.get("c2_context") or {}).get("evidence_state"),
        "policy_state": (record.get("c2_context") or {}).get("policy_state"),
        "integrity_checked": result.get("integrity_checked"),
        "native_recomputed": result.get("native_recomputed"),
        "authority_granted": record.get("boundary", {}).get("authority_granted"),
        "execution_permitted": record.get("boundary", {}).get("execution_permitted"),
        "business_action_calls": record.get("boundary", {}).get("business_action_calls"),
    }
