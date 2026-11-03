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

The classification is built from counts, not from the kernel's error codes. Two different
damaged states produce the same code (`REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED` covers both
an orphan claim and a half commit), so the disk shape is what tells them apart.
"""
import hashlib
import json
import os
from pathlib import Path

SCHEMA = "H56_APP_RECOVERY_V1"
LONG_PREFIX = "\\\\?\\"

HEALTHY = "HEALTHY"
EMPTY = "EMPTY"
ORPHAN_CLAIM = "ORPHAN_CLAIM"
HALF_COMMIT = "HALF_COMMIT"
ARTIFACT_MISSING = "ARTIFACT_MISSING"
CLAIM_MISSING = "CLAIM_MISSING"
TORN_JOURNAL = "TORN_JOURNAL"
MIXED = "MIXED"

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


def classify(session_directory):
    """Count the three things the kernel writes, then name the state they describe."""
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

    return dict(
        session=directory.name,
        state=name,
        claims=len(claims),
        artifacts=len(artifacts),
        events=len(events),
        journal_bytes=len(raw),
        journal_complete=(raw.endswith(b"\n") if raw else None),
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
    path = Path(session_directory) / "artifacts" / (assessment_id[7:] + ".json")
    if not path.is_file():
        raise RecoveryError("RECOVERY_ARTIFACT_MISSING", assessment_id[:22])
    raw = _read(path)
    measured = hashlib.sha256(raw).hexdigest()
    if measured != payload.get("artifact_sha256"):
        raise RecoveryError("RECOVERY_ARTIFACT_DRIFT", assessment_id[:22])
    return json.loads(raw.decode("utf-8")), measured


def restore(records_root, session, run_directory):
    """Write `recovery.json` beside a run whose kernel side survived.

    What this can state: which assessment, which decision, how many native calls, what the
    boundary said, and the two hashes that tie those to the journal. What it cannot state:
    the order. The kernel never knew about orders; the order entered through `request_id`
    as a one-way digest, so there is nothing to invert.

    Writing `result.json` instead would produce a file that looks like a first-hand run
    summary while containing a second-hand subset. A separate filename is the honest option.
    """
    directory = Path(records_root) / session
    state = classify(directory)
    if state["state"] != HEALTHY:
        raise RecoveryError("RECOVERY_STATE_NOT_RESTORABLE",
                            "%s (%s)" % (state["session"], state["state"]))
    run_path = Path(run_directory)
    if not run_path.is_dir():
        # A bare FileNotFoundError from the write below would be the same unhelpful shape
        # this module complains about in the kernel. Name the condition instead.
        raise RecoveryError("RECOVERY_RUN_DIRECTORY_MISSING", run_path.name)

    _, events = journal_state(_read(directory / "events.jsonl"))
    event = events[-1]
    record, artifact_sha = _artifact_for(directory, event)
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
        "note": ("Second-hand: the verdict is the kernel's, copied from the record store. "
                 "This file is not a run summary and must not be presented as one."),
    }
    target = run_path / "recovery.json"
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    target.write_bytes(payload.encode("utf-8"))
    return document, target
