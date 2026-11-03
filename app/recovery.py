"""Say what state the record store is in, and refuse to repair it.

The kernel does not repair a damaged record store, and says so in its own error name:
`PARTIAL_EVENT_PRESERVED_NO_AUTOREPAIR`. Truncating a torn journal back to its last full
line would make the file parse again, but the event that was half-written is then gone and
the remaining chain no longer describes what happened. That is not repair, it is editing.

So this module has exactly two jobs:

* `survey` reads the disk and classifies each session into one of a fixed set of states.
  It never calls the kernel, because in the torn state the kernel refuses to open the
  session at all, and a survey that cannot look is not a survey.
* `restore` writes one new file, `recovery.json`, beside a run whose kernel side survived
  but whose application side did not. It does not write `result.json`, does not write
  `binding.json`, and does not claim to have recreated either.

The classification is built from counts **and then from the bytes**. Counts alone were not
enough: an artifact rewritten from INFEASIBLE to FEASIBLE, with the journal's
`artifact_sha256` updated to match but the event hash left stale, still has one claim, one
artifact and one event -- the shape of a healthy session. The kernel refused it; this module
called it HEALTHY and `restore` copied the forged verdict out. File counts describe the shape
of a store; they say nothing about whether the store can be believed.

So the content check recomputes what the kernel recomputes, and refuses to certify anything
it cannot recompute:

* the event chain -- `sequence` counting from 1, `previous` chaining, `event_sha256` equalling
  the digest of the event minus that field, exactly as `TaskJournal.read()` requires;
* each artifact against the digest its event names;
* each record's own derivations -- `semantic_sha256`, `decision_id`, `projection_hash`;
* the event payload against the record it points at.

`restore` additionally accepts a `kernel_verifier` callback. Recomputing the chain in this
module is a second opinion, not the primary one: where the kernel can still open the session,
its `view()` is the authority, and a disagreement is a refusal.
"""
import hashlib
import json
from pathlib import Path

SCHEMA = "H56_APP_RECOVERY_V1"
LONG_PREFIX = "\\\\?\\"

GENESIS = "0" * 64
EVENT_KEYS = frozenset(("sequence", "previous", "kind", "payload", "event_sha256"))

HEALTHY = "HEALTHY"
EMPTY = "EMPTY"
ORPHAN_CLAIM = "ORPHAN_CLAIM"
HALF_COMMIT = "HALF_COMMIT"
ARTIFACT_MISSING = "ARTIFACT_MISSING"
CLAIM_MISSING = "CLAIM_MISSING"
TORN_JOURNAL = "TORN_JOURNAL"
MIXED = "MIXED"
CHAIN_BROKEN = "CHAIN_BROKEN"

# Findings from the content check. Named individually because "the store is bad" is not an
# actionable statement: which link failed decides who can fix it.
EVENT_SCHEMA = "RECOVERY_EVENT_SCHEMA"
EVENT_SEQUENCE = "RECOVERY_EVENT_SEQUENCE"
EVENT_CHAIN = "RECOVERY_EVENT_CHAIN"
EVENT_HASH = "RECOVERY_EVENT_HASH"
RECORD_SCHEMA = "RECOVERY_RECORD_SCHEMA"
RECORD_SEMANTIC = "RECOVERY_RECORD_SEMANTIC"
RECORD_DECISION_ID = "RECOVERY_RECORD_DECISION_ID"
RECORD_PROJECTION = "RECOVERY_RECORD_PROJECTION"
EVENT_RECORD_BINDING = "RECOVERY_EVENT_RECORD_BINDING"
# Same conditions `_artifact_for()` raises on, named for the findings list. Kept separate
# from the state constants above because a state names a session and a finding names a link.
ARTIFACT_ABSENT = "RECOVERY_ARTIFACT_MISSING"
ARTIFACT_DRIFT = "RECOVERY_ARTIFACT_DRIFT"


# Whether the state blocks the ability to reach a verdict, and whether this tool will act.
ADVICE = {
    HEALTHY: "No action. The session is complete and every event parses.",
    EMPTY: "No action. The session directory holds nothing yet.",
    ORPHAN_CLAIM: (
        "A reservation exists with no journal event and no artifact: the process died "
        "between reserve() and commit(). The kernel refuses to clear this itself, because "
        "an automatic sweep cannot tell a dead writer from a live one. Either run the same "
        "intent again under a new run stamp, or have someone with authority delete "
        "claims/<key>.json and record that decision. This tool will not delete it."),
    HALF_COMMIT: (
        "The artifact exists but the journal event does not: the process died between "
        "writing the artifact and appending the event. Appending the missing event by hand "
        "would invent a commit the journal never made. The assessment must be re-run under "
        "a new run stamp; the orphan artifact is inert and should be left for an auditor."),
    ARTIFACT_MISSING: (
        "An event points at an artifact that is not there. Reading this session through the "
        "kernel raises a bare FileNotFoundError rather than a coded refusal, so callers must "
        "treat an unexplained FileNotFoundError as this state. The verdict cannot be "
        "re-checked."),
    CLAIM_MISSING: (
        "The journal and artifact are intact, so the verdict still verifies; only the "
        "reservation is gone. Re-submitting the same request will be refused with "
        "COMMITTED_CLAIM_MISSING, so replay is closed for this session. Existing evidence is "
        "unaffected."),
    TORN_JOURNAL: (
        "The journal's last line is incomplete. The kernel refuses the whole session with "
        "PARTIAL_EVENT_PRESERVED_NO_AUTOREPAIR: not one event is readable, because a partial "
        "line could mean the tail event was never committed. Cutting the damaged line clean "
        "would manufacture a consistent-looking history, so the verdict must be "
        "re-established under a new session."),
    MIXED: (
        "Counts do not fit any single state: more artifacts than events, or claims and events "
        "that disagree. Treat as unknown until someone reads the files by hand; this tool "
        "reports the counts and stops."),
    CHAIN_BROKEN: (
        "The file counts look like a complete session, but the bytes do not hold together: an "
        "event hash, a previous-link, an artifact digest, or a record's own derivation "
        "disagrees. The kernel refuses this session; treating the counts as health is exactly "
        "how a forged verdict gets copied out. Do not restore from it. The verdict must be "
        "re-established under a new session, and the disagreement preserved for an auditor."),
}


class RecoveryError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def _read(path):
    with open(LONG_PREFIX + str(path), "rb") as handle:
        return handle.read()


def journal_state(raw):
    """Return (state, events) using only what the bytes say.

    `TORN` is not "the last event looks odd"; it is "the file does not end in a newline",
    which is the exact condition the kernel refuses on. Keeping the test identical to the
    kernel's is what makes the classification agree with the refusal.
    """
    if not raw:
        return "MISSING", []
    if not raw.endswith(b"\n"):
        return "TORN", []
    events = []
    for line in raw.split(b"\n"):
        if not line:
            continue
        try:
            events.append(json.loads(line.decode("utf-8")))
        except ValueError:
            return "TORN", []
    return "OK", events


def canonical_text(value):
    """Byte-for-byte the kernel's `canonical()`; the digests below are compared to its own."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def digest_of(value):
    return hashlib.sha256(canonical_text(value).encode("utf-8")).hexdigest()


def record_findings(record):
    """Recompute the three derivations `verify_record()` pins inside a record.

    A record is not an opaque blob: it carries `semantic_sha256` over its own fields,
    `decision_id` over the assessment and that digest, and `projection_hash` over the
    projection. Flipping `c2_projection.decision` breaks the projection hash and the semantic
    digest even when every journal hash has been recomputed to match the new bytes.
    """
    if not isinstance(record, dict):
        return [RECORD_SCHEMA]
    found = []
    body = {key: value for key, value in record.items()
            if key not in ("semantic_sha256", "decision_id")}
    if record.get("semantic_sha256") != digest_of(body):
        found.append(RECORD_SEMANTIC)
    expected_id = "DECISION:" + digest_of(dict(assessment_id=body.get("assessment_id"),
                                               semantic_sha256=record.get("semantic_sha256")))
    if record.get("decision_id") != expected_id:
        found.append(RECORD_DECISION_ID)
    projection = body.get("c2_projection")
    if projection is not None:
        if not isinstance(projection, dict):
            found.append(RECORD_PROJECTION)
        elif projection.get("projection_hash") != digest_of(
                {key: value for key, value in projection.items() if key != "projection_hash"}):
            found.append(RECORD_PROJECTION)
    return found


def artifact_path(session_directory, assessment_id):
    return Path(session_directory) / "artifacts" / (assessment_id[7:] + ".json")


def event_findings(session_directory, event):
    """One event: its artifact, the record inside it, and that record against the payload."""
    if not isinstance(event, dict) or set(event) != {"sequence", "previous", "kind",
                                                     "payload", "event_sha256"}:
        return [EVENT_SCHEMA]
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return [EVENT_SCHEMA]
    assessment_id = payload.get("assessment_id")
    if not isinstance(assessment_id, str) or not assessment_id.startswith("ASSESS:"):
        return [EVENT_SCHEMA]
    path = artifact_path(session_directory, assessment_id)
    if not path.is_file():
        return [ARTIFACT_ABSENT]
    try:
        raw = _read(path)
    except OSError:
        return [ARTIFACT_ABSENT]
    if hashlib.sha256(raw).hexdigest() != payload.get("artifact_sha256"):
        return [ARTIFACT_DRIFT]
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [RECORD_SCHEMA]
    found = record_findings(record)
    if isinstance(record, dict):
        for key in ("assessment_id", "decision_id", "semantic_sha256"):
            if record.get(key) != payload.get(key):
                found.append(EVENT_RECORD_BINDING)
                break
    return found


def content_findings(session_directory, events):
    """The whole chain, in order: one break makes every later link unverifiable."""
    found = []
    previous = GENESIS
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict) or set(event) != EVENT_KEYS:
            found.append(EVENT_SCHEMA)
            return found
        core = {key: value for key, value in event.items() if key != "event_sha256"}
        if type(event.get("sequence")) is not int or event["sequence"] != index:
            found.append(EVENT_SEQUENCE)
        if event.get("previous") != previous:
            found.append(EVENT_CHAIN)
        if digest_of(core) != event.get("event_sha256"):
            found.append(EVENT_HASH)
        previous = event.get("event_sha256")
        found.extend(event_findings(session_directory, event))
    return found


def classify(session_directory):
    """Count the three things the kernel writes, then check whether the counts are honest.

    The shape decides the name only while the bytes agree. Counts that look complete but
    content that fails is not HEALTHY; it is `CHAIN_BROKEN`, because that is the case where
    trusting the count would launder a forgery.
    """
    directory = Path(session_directory)
    claims = sorted((directory / "claims").glob("*.json"))
    artifacts = sorted((directory / "artifacts").glob("*.json"))
    journal = directory / "events.jsonl"
    raw = _read(journal) if journal.is_file() else b""
    state, events = journal_state(raw)

    if state == "TORN":
        name = TORN_JOURNAL
    elif not claims and not artifacts and not events:
        name = EMPTY
    elif not events and claims and not artifacts:
        name = ORPHAN_CLAIM
    elif not events and claims and artifacts:
        name = HALF_COMMIT
    elif events and not artifacts:
        name = ARTIFACT_MISSING
    elif events and not claims:
        name = CLAIM_MISSING
    elif len(events) == len(artifacts):
        name = HEALTHY
    else:
        name = MIXED

    findings = []
    verified = None
    if events and name in (HEALTHY, MIXED):
        findings = content_findings(directory, events)
        verified = not findings
        if findings:
            name = CHAIN_BROKEN

    return dict(
        session=directory.name,
        state=name,
        claims=len(claims),
        artifacts=len(artifacts),
        events=len(events),
        journal_bytes=len(raw),
        journal_complete=(raw.endswith(b"\n") if raw else None),
        verified=verified,
        findings=findings,
        advice=ADVICE[name],
    )


def survey(records_root):
    """Every session under the root, classified. Read-only, no kernel import."""
    root = Path(records_root)
    if not root.is_dir():
        raise RecoveryError("RECORDS_ROOT_MISSING", str(root))
    rows = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("oq_"):
            continue
        rows.append(classify(entry))
    return rows


def _artifact_for(session_directory, event):
    """Read the artifact an event names, and check it still hashes to what the event says."""
    payload = event.get("payload") or {}
    assessment_id = payload.get("assessment_id") or ""
    if not assessment_id.startswith("ASSESS:"):
        raise RecoveryError("RECOVERY_EVENT_SCHEMA", assessment_id[:32])
    path = artifact_path(session_directory, assessment_id)
    if not path.is_file():
        raise RecoveryError("RECOVERY_ARTIFACT_MISSING", assessment_id[:22])
    raw = _read(path)
    measured = hashlib.sha256(raw).hexdigest()
    if measured != payload.get("artifact_sha256"):
        raise RecoveryError("RECOVERY_ARTIFACT_DRIFT", assessment_id[:22])
    return json.loads(raw.decode("utf-8")), measured


def reference_for(event):
    """The five-field reference the kernel's `view()` takes, rebuilt from one event."""
    payload = event["payload"]
    return dict(assessment_id=payload["assessment_id"],
                decision_id=payload["decision_id"],
                semantic_sha256=payload["semantic_sha256"],
                artifact_sha256=payload["artifact_sha256"],
                journal_event_sha256=event["event_sha256"])


def restore(records_root, session, run_directory, kernel_verifier=None):
    """Write `recovery.json` beside a run whose kernel side survived.

    What this can state: which assessment, which decision, how many native calls, what the
    boundary said, and the two hashes that tie those to the journal. What it cannot state:
    the order. The kernel never knew about orders; the order entered through `request_id`
    as a one-way digest, so there is nothing to invert.

    Writing `result.json` instead would produce a file that looks like a first-hand run
    summary while containing a second-hand subset. A separate filename is the honest option.

    `kernel_verifier(session, reference)` returns the record the kernel would show for that
    reference, or raises. It is a parameter rather than an import because this module must
    classify a store the kernel has already refused; the caller decides whether the kernel is
    reachable. When it is reachable, its answer outranks this module's recomputation: the
    audit that found this gap did not do so by re-deriving hashes, it did so by asking the
    kernel and getting a refusal. A refusal there is a refusal here.
    """
    directory = Path(records_root) / session
    state = classify(directory)
    if state["state"] != HEALTHY:
        detail = "%s (%s" % (state["session"], state["state"])
        if state["findings"]:
            detail += " " + ",".join(sorted(set(state["findings"])))
        raise RecoveryError("RECOVERY_STATE_NOT_RESTORABLE", detail + ")")
    run_path = Path(run_directory)
    if not run_path.is_dir():
        # A bare FileNotFoundError from the write below would be the same unhelpful shape
        # this module complains about in the kernel. Name the condition instead.
        raise RecoveryError("RECOVERY_RUN_DIRECTORY_MISSING", run_path.name)

    _, events = journal_state(_read(directory / "events.jsonl"))
    event = events[-1]
    record, artifact_sha = _artifact_for(directory, event)

    # The full read-only check, before a single byte is written. `classify` already recomputed
    # the chain and the record's derivations; this repeats the record part on the object that
    # is about to be copied, so a change between the two reads cannot slip through.
    residual = record_findings(record)
    if residual:
        raise RecoveryError("RECOVERY_RECORD_INCONSISTENT", ",".join(sorted(set(residual))))

    kernel_record = None
    if kernel_verifier is not None:
        try:
            kernel_record = kernel_verifier(session, reference_for(event))
        except Exception as error:  # noqa: BLE001 - any refusal here is the verdict
            # `TaskStoreError` carries its code in the message rather than in an attribute,
            # so falling back to the class name would report "TaskStoreError" for every kind
            # of refusal -- including the one this whole check exists to catch.
            code = getattr(error, "code", None) or str(error).split(":")[0].strip() \
                or type(error).__name__
            raise RecoveryError("RECOVERY_KERNEL_REFUSED", code[:64]) from error
        if not isinstance(kernel_record, dict):
            raise RecoveryError("RECOVERY_KERNEL_REFUSED", "no record returned")
        for key in ("assessment_id", "decision_id", "semantic_sha256"):
            if kernel_record.get(key) != record.get(key):
                raise RecoveryError("RECOVERY_KERNEL_DISAGREES", key)
        ours = (record.get("c2_projection") or {}).get("decision")
        theirs = (kernel_record.get("c2_projection") or {}).get("decision")
        if ours != theirs:
            raise RecoveryError("RECOVERY_KERNEL_DISAGREES", "decision")

    projection = record.get("c2_projection") or {}
    calls = (record.get("mapping_trace") or {}).get("native_calls") or []
    distribution = {}
    for call in calls:
        distribution[call.get("source")] = distribution.get(call.get("source"), 0) + 1

    document = {
        "schema": SCHEMA,
        "recovered_from": "RECORD_STORE",
        "session": session,
        "assessment_id": record.get("assessment_id"),
        "decision_id": record.get("decision_id"),
        "decision": projection.get("decision", "NO_DECISION"),
        "stage": record.get("stage"),
        "native_calls": len(calls),
        "native_distribution": distribution,
        "boundary": dict(record.get("boundary") or {}),
        "semantic_sha256": record.get("semantic_sha256"),
        "artifact_sha256": artifact_sha,
        "journal_event_sha256": event.get("event_sha256"),
        "order_recoverable": False,
        "order_note": ("The order reached the kernel only as a digest inside request_id. "
                       "It cannot be inverted, so this recovery carries no order fields."),
        "result_json_restored": False,
        "binding_json_restored": False,
        "verification": {
            "chain_recomputed": True,
            "record_recomputed": True,
            "kernel_consulted": kernel_verifier is not None,
            "kernel_record_sha256": (None if kernel_record is None
                                     else digest_of(kernel_record)),
        },
        "note": ("Second-hand: the verdict is the kernel's, copied from the record store. "
                 "This file is not a run summary and must not be presented as one."),
    }
    target = run_path / "recovery.json"
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    target.write_bytes(payload.encode("utf-8"))
    return document, target
