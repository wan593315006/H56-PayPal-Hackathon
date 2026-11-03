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


def record(*, decision="FEASIBLE", calls=22):
    return {
        "assessment_id": ASSESSMENT,
        "decision_id": "DECIDE:" + "b" * 64,
        "semantic_sha256": "c" * 64,
        "stage": "COMPLETE",
        "c2_projection": {"decision": decision},
        "mapping_trace": {"native_calls": [{"source": "K0"}] * calls},
        "boundary": {"authority_granted": False, "execution_permitted": False,
                     "business_action_calls": 0},
    }


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
    event = dict(core, event_sha256=hashlib.sha256(canonical(core).encode()).hexdigest())
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
                     recovery.CLAIM_MISSING, recovery.TORN_JOURNAL, recovery.MIXED):
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

    def test_detects_an_artifact_that_drifted(self):
        """The event names a hash; a rewritten artifact must not be presented as recovered."""
        build_session(self.records)
        artifact = next((self.records / SESSION / "artifacts").iterdir())
        artifact.write_bytes(artifact.read_bytes() + b" ")
        run = self.runs / "20260101T000000Z_test"
        run.mkdir()
        with self.assertRaises(recovery.RecoveryError) as caught:
            recovery.restore(self.records, SESSION, run)
        self.assertEqual(caught.exception.code, "RECOVERY_ARTIFACT_DRIFT")

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


if __name__ == "__main__":
    unittest.main()
