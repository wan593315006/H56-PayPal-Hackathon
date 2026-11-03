"""The read-only UI's three refusals, at unit level.

The end-to-end versions live in `构建脚本/probe_ui_boundary.py`, which starts the real server
and speaks HTTP at it. These are the same rules reduced to the functions that make them, so a
regression shows up in the ordinary test run rather than only when someone starts a server.

Two of them are about a distinction that is easy to lose:

* a directory junction is not a symlink, and `Path.is_symlink()` returns False for it. The
  name is inside `runs/`; the bytes are outside.
* a verdict is evidence about one assessment. Matching it by timestamp is matching by
  coincidence -- two businesses can share a stamp and disagree.
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "ui" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("h56_ui_server_under_test", str(SERVER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load_server()


def junction(link, target):
    finished = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, text=True)
    return finished.returncode == 0 and Path(link).is_dir()


def write_json(path, payload):
    path.write_bytes(json.dumps(payload, sort_keys=True,
                                separators=(",", ":")).encode("utf-8"))


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.path = Path(self.scratch.name) / "events.jsonl"

    def tearDown(self):
        self.scratch.cleanup()

    def test_a_complete_journal_is_ok(self):
        self.path.write_bytes(b'{"sequence":1}\n')
        self.assertEqual(server.parse_journal(self.path)["journal_state"], "OK")

    def test_a_missing_trailing_newline_is_torn(self):
        """The kernel refuses this exact shape; the UI used to pop the empty segment and say OK."""
        self.path.write_bytes(b'{"sequence":1}')
        self.assertEqual(server.parse_journal(self.path)["journal_state"], "TORN")

    def test_an_unparsable_line_is_torn(self):
        self.path.write_bytes(b"not json\n")
        state = server.parse_journal(self.path)
        self.assertEqual(state["journal_state"], "TORN")
        self.assertEqual(state["damaged_line"], 1)

    def test_missing_and_unreadable_are_named(self):
        self.assertEqual(server.parse_journal(self.path)["journal_state"], "MISSING")

    def test_the_rule_matches_the_recovery_module(self):
        """Two verdicts about one file is how a display layer starts disagreeing with the kernel."""
        try:
            from app import recovery
        except ImportError:  # pragma: no cover - the test tree should always have app/
            self.skipTest("app.recovery unavailable")
        for raw in (b"", b'{"sequence":1}\n', b'{"sequence":1}', b"not json\n",
                    b'{"a":1}\n{"b":2}\n'):
            with self.subTest(raw=raw[:12]):
                self.path.write_bytes(raw)
                self.assertEqual(server.parse_journal(self.path)["journal_state"],
                                 recovery.journal_state(raw)[0])


class BoundaryTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.base = Path(self.scratch.name)
        self.root = self.base / "runs"
        self.root.mkdir()

    def tearDown(self):
        self.scratch.cleanup()

    def test_a_plain_directory_is_accepted(self):
        inside = self.root / "20260101T000000Z_shop"
        inside.mkdir()
        self.assertIsNotNone(server.resolve_within(inside, self.root))

    def test_a_directory_junction_is_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "result.json").write_bytes(b'{"marker":"x"}')
        link = self.root / "20260101T000000Z_shop"
        if not junction(link, outside):
            self.skipTest("junction could not be created in this environment")
        self.assertTrue(server.is_reparse(link))
        self.assertIsNone(server.resolve_within(link, self.root))
        self.assertIsNone(server.resolve_within(link / "result.json", self.root))

    def test_a_path_outside_the_root_is_refused(self):
        outside = self.base / "elsewhere"
        outside.mkdir()
        self.assertIsNone(server.resolve_within(outside, self.root))

    def test_a_linked_root_is_refused(self):
        """If `runs/` itself is a junction, no name inside it can be reasoned about."""
        real = self.base / "real_runs"
        real.mkdir()
        linked = self.base / "linked_runs"
        if not junction(linked, real):
            self.skipTest("junction could not be created in this environment")
        self.assertIsNone(server.resolve_within(linked / "anything", linked))


class RecordDecisionTest(unittest.TestCase):
    """A verdict may only be attached to the assessment it was made about."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.base = Path(self.scratch.name)
        self.runs = self.base / "runs"
        self.records = self.base / "records"
        self.runs.mkdir()
        self.records.mkdir()
        self._saved = (server.RUNS_DIR, server.RECORDS_DIR)
        server.RUNS_DIR, server.RECORDS_DIR = self.runs, self.records
        self.stamp = "20260102T000000Z"

    def tearDown(self):
        server.RUNS_DIR, server.RECORDS_DIR = self._saved
        self.scratch.cleanup()

    def make_session(self, business, assessment, decision, artifact_decision=None):
        session = self.records / ("oq_%s_%s" % (business, self.stamp))
        (session / "artifacts").mkdir(parents=True)
        (session / "claims").mkdir()
        (session / "events.jsonl").write_bytes(b'{"sequence":1}\n')
        write_json(session / "artifacts" / (assessment[7:] + ".json"),
                   {"assessment_id": assessment,
                    "c2_projection": {"decision": artifact_decision or decision}})
        return session

    def make_run(self, business, assessment, decision):
        run = self.runs / ("%s_%s" % (self.stamp, business))
        run.mkdir()
        write_json(run / "result.json",
                   {"decision": decision, "assessment_id": assessment,
                    "reference": {"assessment_id": assessment}})
        return run

    def rows(self):
        return {row["session"]: row for row in server.api_records()}

    def test_a_verdict_is_not_borrowed_from_another_business(self):
        alpha_assessment = "ASSESS:" + "1" * 64
        beta_assessment = "ASSESS:" + "2" * 64
        self.make_session("alpha", alpha_assessment, "FEASIBLE")
        self.make_session("beta", beta_assessment, "INFEASIBLE")
        self.make_run("alpha", alpha_assessment, "FEASIBLE")
        beta_run = self.make_run("beta", beta_assessment, "INFEASIBLE")
        (beta_run / "result.json").unlink()

        rows = self.rows()
        self.assertEqual(rows["oq_alpha_%s" % self.stamp]["decision"], "FEASIBLE")
        beta = rows["oq_beta_%s" % self.stamp]
        self.assertIsNone(beta["decision"])
        self.assertEqual(beta["decision_source"], "NO_MATCH")

    def test_a_conflicting_artifact_verdict_is_flagged(self):
        assessment = "ASSESS:" + "3" * 64
        self.make_session("alpha", assessment, "FEASIBLE", artifact_decision="INFEASIBLE")
        self.make_run("alpha", assessment, "FEASIBLE")
        row = self.rows()["oq_alpha_%s" % self.stamp]
        self.assertEqual(row["decision"], "FEASIBLE")
        self.assertEqual(row["artifact_decision"], "INFEASIBLE")
        self.assertTrue(row["decision_conflict"])

    def test_a_matching_artifact_is_not_flagged(self):
        assessment = "ASSESS:" + "4" * 64
        self.make_session("alpha", assessment, "FEASIBLE")
        self.make_run("alpha", assessment, "FEASIBLE")
        row = self.rows()["oq_alpha_%s" % self.stamp]
        self.assertFalse(row["decision_conflict"])

    def test_a_linked_session_is_not_read(self):
        outside = self.base / "outside"
        (outside / "artifacts").mkdir(parents=True)
        write_json(outside / "artifacts" / ("5" * 64 + ".json"),
                   {"assessment_id": "ASSESS:" + "5" * 64,
                    "c2_projection": {"decision": "FEASIBLE"}})
        link = self.records / ("oq_link_%s" % self.stamp)
        if not junction(link, outside):
            self.skipTest("junction could not be created in this environment")
        self.assertEqual(server.api_records(), [])
        refused = [row["entry"] for row in server.api_refused()]
        self.assertIn("oq_link_%s" % self.stamp, refused)


if __name__ == "__main__":
    unittest.main()
