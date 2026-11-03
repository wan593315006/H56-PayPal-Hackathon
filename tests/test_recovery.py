"""P2: classify a damaged record store, and recover without editing it.

These cases build the six disk shapes by hand rather than by crashing a process. That is
deliberate: the crash path is covered by `构建脚本/probe_p2_crash.py`, which needs child
processes and several seconds of four-core work per point. A unit test that poked the same
boundaries would be slow and would still not prove the crash produced the shape -- only the
probe can do that. What these tests pin down is the *classification and recovery contract*,
which must hold for every shape regardless of how it came to be.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app import recovery

SESSION = "oq_test_20260101T000000Z"
ASSESSMENT = "ASSESS:" + "a" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def record(*, decision="FEASIBLE", calls=22):
    """A record with the three derivations the kernel pins, not just the shape of one.

    The first version of this fixture used `"c" * 64` for `semantic_sha256` and a made-up
    `decision_id`. That was a record the kernel would itself reject, used as the HEALTHY
    baseline -- which meant the tests agreed with a definition of healthy that no real store
    ever satisfies. It also hid the exact forgery the audit found: changing `decision` without
    recomputing the derivations is now a *content* failure, and the fixture has to be strong
    enough to tell the difference.
    """
    projection = {"decision": decision, "candidate_planning_only": True,
                  "authority_granted": False, "execution_permitted": False}
    projection["projection_hash"] = digest(projection)
    body = {
        "assessment_id": ASSESSMENT,
        "stage": "COMPLETE",
        "evidence_grade": "MACHINE_CHECKED",
        "c2_projection": projection,
        "mapping_trace": {"native_calls": [{"source": "K0"}] * calls},
        "boundary": {"authority_granted": False, "execution_permitted": False,
                     "business_action_calls": 0},
    }
    body["semantic_sha256"] = digest(body)
    body["decision_id"] = "DECISION:" + digest(dict(assessment_id=ASSESSMENT,
                                                    semantic_sha256=body["semantic_sha256"]))
    return body


def build_session(root, name=SESSION, claims=1, artifacts=1, events=1,
                  torn=False, decision="FEASIBLE", calls=22):
    directory = Path(root) / name
    (directory / "claims").mkdir(parents=True)
    (directory / "artifacts").mkdir()

    body = record(decision=decision, calls=calls)
    raw = canonical(body).encode("utf-8")
    artifact_sha = hashlib.sha256(raw).hexdigest()
    (directory / "artifacts" / (ASSESSMENT[7:] + ".json")).write_bytes(raw)

    for index in range(claims):
        (directory / "claims" / ("%064x.json" % (index + 1))).write_bytes(
            canonical({"schema": "H56_ASSESSMENT_CLAIM_V1",
                       "idempotency_key": "%064x" % (index + 1)}).encode("utf-8"))

    payload = {"idempotency_key": "%064x" % 1, "request_digest": "d" * 64,
               "assessment_id": ASSESSMENT, "decision_id": body["decision_id"],
               "semantic_sha256": body["semantic_sha256"], "artifact_sha256": artifact_sha}
    core = {"sequence": 1, "previous": "0" * 64, "kind": "ASSESSMENT_RECORDED",
            "payload": payload}
    event = dict(core, event_sha256=digest(core))
    text = canonical(event) + ("\n" if events else "")
    if events:
        (directory / "events.jsonl").write_bytes(text.encode("utf-8"))
    if torn:
        line = text[:-1]
        (directory / "events.jsonl").write_bytes(line[:-30].encode("utf-8"))

    if not artifacts:
        for item in (directory / "artifacts").iterdir():
            item.unlink()
    if not claims:
        for item in (directory / "claims").iterdir():
            item.unlink()
    return directory


def reread_events(directory):
    raw = (Path(directory) / "events.jsonl").read_bytes()
    return [json.loads(line) for line in raw.split(b"\n") if line]


def rewrite_journal(directory, events, *, reseal=True, renumber=True):
    """Write events back, optionally recomputing each `event_sha256` and the `previous` links.

    With `reseal=False` this is the auditor's exact forgery: the artifact and the digest that
    names it are updated, the event hash is left stale. With `reseal=True` the chain is made
    internally consistent again, which is the harder case -- only the record's own derivations
    still disagree.

    `renumber=False` keeps the `sequence` values as given, so a gap can be written on purpose.
    """
    previous = "0" * 64
    rows = []
    for index, event in enumerate(events, start=1):
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        if renumber:
            body["sequence"] = index
        body["previous"] = previous
        if reseal:
            body["event_sha256"] = digest(body)
        else:
            body["event_sha256"] = event["event_sha256"]
        previous = body["event_sha256"]
        rows.append(body)
    payload = b"".join((canonical(row) + "\n").encode("utf-8") for row in rows)
    (Path(directory) / "events.jsonl").write_bytes(payload)


def flip_the_artifact(directory, decision="FEASIBLE"):
    """Rewrite the artifact's decision in place and return its new digest."""
    path = Path(directory) / "artifacts" / (ASSESSMENT[7:] + ".json")
    body = json.loads(path.read_bytes().decode("utf-8"))
    body["c2_projection"]["decision"] = decision
    raw = canonical(body).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class JournalStateTest(unittest.TestCase):
    def test_no_file_is_missing(self):
        self.assertEqual(recovery.journal_state(b""), ("MISSING", []))

    def test_no_trailing_newline_is_torn(self):
        state, events = recovery.journal_state(b'{"sequence":1}')
        self.assertEqual(state, "TORN")
        self.assertEqual(events, [])

    def test_complete_line_parses(self):
        state, events = recovery.journal_state(b'{"sequence":1}\n')
        self.assertEqual(state, "OK")
        self.assertEqual(len(events), 1)

    def test_unparsable_line_is_torn_not_partial(self):
        """A full line that is not JSON is still 'cannot read', and must not be read as empty."""
        state, events = recovery.journal_state(b"not json\n")
        self.assertEqual(state, "TORN")
        self.assertEqual(events, [])


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)

    def tearDown(self):
        self.scratch.cleanup()

    def state_of(self, **shape):
        build_session(self.root, **shape)
        return recovery.classify(self.root / SESSION)["state"]

    def test_healthy(self):
        self.assertEqual(self.state_of(), recovery.HEALTHY)

    def test_empty(self):
        self.assertEqual(self.state_of(claims=0, artifacts=0, events=0), recovery.EMPTY)

    def test_orphan_claim(self):
        self.assertEqual(self.state_of(artifacts=0, events=0), recovery.ORPHAN_CLAIM)

    def test_half_commit(self):
        self.assertEqual(self.state_of(events=0), recovery.HALF_COMMIT)

    def test_artifact_missing(self):
        self.assertEqual(self.state_of(artifacts=0), recovery.ARTIFACT_MISSING)

    def test_claim_missing(self):
        self.assertEqual(self.state_of(claims=0), recovery.CLAIM_MISSING)

    def test_torn_journal(self):
        self.assertEqual(self.state_of(torn=True), recovery.TORN_JOURNAL)

    def test_every_state_carries_advice(self):
        for name in (recovery.HEALTHY, recovery.EMPTY, recovery.ORPHAN_CLAIM,
                     recovery.HALF_COMMIT, recovery.ARTIFACT_MISSING,
                     recovery.CLAIM_MISSING, recovery.TORN_JOURNAL, recovery.MIXED,
                     recovery.CHAIN_BROKEN):
            self.assertIn(name, recovery.ADVICE)

    def test_survey_skips_directories_that_are_not_sessions(self):
        build_session(self.root)
        (self.root / "artifacts").mkdir()
        (self.root / "claims").mkdir()
        rows = recovery.survey(self.root)
        self.assertEqual([row["session"] for row in rows], [SESSION])


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.base = Path(self.scratch.name)
        self.records = self.base / "records"
        self.records.mkdir()
        self.runs = self.base / "runs"
        self.runs.mkdir()

    def tearDown(self):
        self.scratch.cleanup()

    def digest(self, root):
        h = hashlib.sha256()
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                h.update(path.relative_to(root).as_posix().encode("utf-8"))
                h.update(path.read_bytes())
        return h.hexdigest()

    def test_writes_recovery_json_and_refuses_an_order(self):
        build_session(self.records, decision="INFEASIBLE", calls=17)
        run = self.runs / "20260101T000000Z_test"
        run.mkdir()
        document, target = recovery.restore(self.records, SESSION, run)
        self.assertEqual(target.name, "recovery.json")
        self.assertFalse((run / "result.json").exists())
        self.assertFalse((run / "binding.json").exists())
        self.assertEqual(document["decision"], "INFEASIBLE")
        self.assertEqual(document["native_calls"], 17)
        self.assertFalse(document["order_recoverable"])
        self.assertFalse(document["result_json_restored"])
        self.assertNotIn("order", document)

    def test_the_written_file_round_trips(self):
        build_session(self.records)
        run = self.runs / "20260101T000000Z_test"
        run.mkdir()
        document, target = recovery.restore(self.records, SESSION, run)
        self.assertEqual(json.loads(target.read_bytes().decode("utf-8")), document)

    def test_does_not_modify_the_record_store(self):
        build_session(self.records)
        run = self.runs / "20260101T000000Z_test"
        run.mkdir()
        before = self.digest(self.records)
        recovery.restore(self.records, SESSION, run)
        self.assertEqual(self.digest(self.records), before)

    def test_refuses_every_state_but_healthy(self):
        shapes = {
            recovery.ORPHAN_CLAIM: dict(artifacts=0, events=0),
            recovery.HALF_COMMIT: dict(events=0),
            recovery.ARTIFACT_MISSING: dict(artifacts=0),
            recovery.CLAIM_MISSING: dict(claims=0),
            recovery.TORN_JOURNAL: dict(torn=True),
        }
        for expected, shape in shapes.items():
            with self.subTest(state=expected):
                name = "oq_" + expected.lower()
                build_session(self.records, name=name, **shape)
                run = self.runs / expected
                run.mkdir()
                with self.assertRaises(recovery.RecoveryError) as caught:
                    recovery.restore(self.records, name, run)
                self.assertEqual(caught.exception.code, "RECOVERY_STATE_NOT_RESTORABLE")

    def test_a_drifted_artifact_never_reaches_the_writer(self):
        """The event names a hash; a rewritten artifact must not be presented as recovered.

        This used to be caught by `_artifact_for` alone, inside `restore`. It is now caught one
        layer earlier, by the content check that decides whether the session is HEALTHY at
        all -- which is the point: the state gate refuses before any code decides to copy.
        The finding still names the drift, so an operator can tell it from a torn journal.
        """
        build_session(self.records)
        artifact = next((self.records / SESSION / "artifacts").iterdir())
        artifact.write_bytes(artifact.read_bytes() + b" ")
        run = self.runs / "20260101T000000Z_test"
        run.mkdir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run)
        self.assertEqual(caught.exception.code, "RECOVERY_STATE_NOT_RESTORABLE")
        self.assertIn(recovery.ARTIFACT_DRIFT, str(caught.exception))
        self.assertFalse((run / "recovery.json").exists())

    def test_refuses_a_missing_run_directory_by_name(self):
        """A bare FileNotFoundError here would repeat the kernel's unhelpful shape."""
        build_session(self.records)
        missing = self.runs / "does-not-exist"
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, missing)
        self.assertEqual(caught.exception.code, "RECOVERY_RUN_DIRECTORY_MISSING")
        self.assertFalse(missing.exists())

    def test_missing_records_root_is_named(self):
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.survey(self.base / "nope")
        self.assertEqual(caught.exception.code, "RECORDS_ROOT_MISSING")


class ChainIntegrityTest(unittest.TestCase):
    """The auditor's forgery: counts that look complete over content that does not.

    One claim, one artifact, one event. Flip the artifact's decision, update the digest the
    journal records for it, leave the event hash stale. The kernel refuses the session. Before
    this check, `classify` called it HEALTHY and `restore` wrote FEASIBLE.
    """

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.base = Path(self.scratch.name)
        self.records = self.base / "records"
        self.records.mkdir()
        self.runs = self.base / "runs"
        self.runs.mkdir()
        self.session_dir = build_session(self.records, decision="INFEASIBLE")

    def tearDown(self):
        self.scratch.cleanup()

    def run_dir(self, name="run"):
        path = self.runs / name
        path.mkdir()
        return path

    def test_a_stale_event_hash_is_not_healthy(self):
        new_sha = flip_the_artifact(self.session_dir, "FEASIBLE")
        events = reread_events(self.session_dir)
        events[0]["payload"]["artifact_sha256"] = new_sha
        rewrite_journal(self.session_dir, events, reseal=False)

        row = recovery.classify(self.session_dir)
        self.assertEqual(row["state"], recovery.CHAIN_BROKEN)
        self.assertFalse(row["verified"])
        self.assertIn(recovery.EVENT_HASH, row["findings"])

        run = self.run_dir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run)
        self.assertEqual(caught.exception.code, "RECOVERY_STATE_NOT_RESTORABLE")
        self.assertFalse((run / "recovery.json").exists())

    def test_a_recomputed_chain_still_fails_the_record_derivations(self):
        """The harder forgery: every journal hash agrees with the new bytes.

        The chain is consistent, so nothing about the journal is anomalous. What still
        disagrees is the record's own arithmetic -- `projection_hash` and `semantic_sha256`
        are derived from the fields that were edited and were not recomputed. A check that
        only walked the journal would call this healthy.
        """
        new_sha = flip_the_artifact(self.session_dir, "FEASIBLE")
        events = reread_events(self.session_dir)
        events[0]["payload"]["artifact_sha256"] = new_sha
        rewrite_journal(self.session_dir, events, reseal=True)

        row = recovery.classify(self.session_dir)
        self.assertEqual(row["state"], recovery.CHAIN_BROKEN)
        self.assertIn(recovery.RECORD_PROJECTION, row["findings"])
        self.assertIn(recovery.RECORD_SEMANTIC, row["findings"])
        self.assertNotIn(recovery.EVENT_HASH, row["findings"])

        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, self.run_dir())
        self.assertIn(recovery.RECORD_PROJECTION, str(caught.exception))

    def test_an_event_pointing_at_a_different_verdict_is_caught(self):
        """Chain intact, artifact intact, but the event and the record no longer agree."""
        events = reread_events(self.session_dir)
        events[0]["payload"]["semantic_sha256"] = "e" * 64
        rewrite_journal(self.session_dir, events, reseal=True)
        row = recovery.classify(self.session_dir)
        self.assertEqual(row["state"], recovery.CHAIN_BROKEN)
        self.assertIn(recovery.EVENT_RECORD_BINDING, row["findings"])

    def test_a_sequence_gap_is_caught(self):
        events = reread_events(self.session_dir)
        extra = json.loads(json.dumps(events[0]))
        rewrite_journal(self.session_dir, [events[0], extra], reseal=True)
        rows = reread_events(self.session_dir)
        rows[1]["sequence"] = 3
        rewrite_journal(self.session_dir, rows, reseal=True, renumber=False)
        row = recovery.classify(self.session_dir)
        self.assertEqual(row["state"], recovery.CHAIN_BROKEN)
        self.assertIn(recovery.EVENT_SEQUENCE, row["findings"])

    def test_the_healthy_baseline_still_passes(self):
        """The control: without this, every rejection above could mean the check is broken."""
        row = recovery.classify(self.session_dir)
        self.assertEqual(row["state"], recovery.HEALTHY)
        self.assertTrue(row["verified"])
        self.assertEqual(row["findings"], [])
        document, target = recovery.restore(self.records, SESSION, self.run_dir())
        self.assertEqual(document["decision"], "INFEASIBLE")
        self.assertTrue(target.is_file())


class KernelVerifierTest(unittest.TestCase):
    """Where the kernel can still open the session, its refusal decides."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.base = Path(self.scratch.name)
        self.records = self.base / "records"
        self.records.mkdir()
        self.runs = self.base / "runs"
        self.runs.mkdir()
        self.session_dir = build_session(self.records, decision="FEASIBLE")
        self.stored = record(decision="FEASIBLE")

    def tearDown(self):
        self.scratch.cleanup()

    def run_dir(self, name="run"):
        path = self.runs / name
        path.mkdir()
        return path

    def test_a_kernel_refusal_is_a_refusal(self):
        class Refused(Exception):
            code = "ASSESSMENT_ARTIFACT_DRIFT"

        def refuse(session, reference):
            raise Refused("drift")

        run = self.run_dir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run, kernel_verifier=refuse)
        self.assertEqual(caught.exception.code, "RECOVERY_KERNEL_REFUSED")
        self.assertIn("ASSESSMENT_ARTIFACT_DRIFT", str(caught.exception))
        self.assertFalse((run / "recovery.json").exists())

    def test_a_kernel_that_returns_nothing_is_not_agreement(self):
        run = self.run_dir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run,
                             kernel_verifier=lambda session, reference: None)
        self.assertEqual(caught.exception.code, "RECOVERY_KERNEL_REFUSED")

    def test_a_kernel_verdict_that_differs_is_a_refusal(self):
        other = record(decision="INFEASIBLE")
        run = self.run_dir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run,
                             kernel_verifier=lambda session, reference: other)
        self.assertEqual(caught.exception.code, "RECOVERY_KERNEL_DISAGREES")

    def test_agreement_is_recorded_in_the_document(self):
        run = self.run_dir()
        document, target = recovery.restore(
            self.records, SESSION, run,
            kernel_verifier=lambda session, reference: self.stored)
        self.assertTrue(document["verification"]["kernel_consulted"])
        self.assertEqual(document["verification"]["kernel_record_sha256"],
                         digest(self.stored))
        self.assertEqual(json.loads(target.read_bytes().decode("utf-8")), document)


if __name__ == "__main__":
    unittest.main()
