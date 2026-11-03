"""Prove the offline entry refuses networking, including swallowed/import-time attempts.

Each control runs in a disposable interpreter: an audit hook cannot be removed, and a
deliberate refusal must not contaminate the parent suite's network-attempt count.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parent.parent / "run_offline_tests.py"


class OfflineGuardTest(unittest.TestCase):
    def run_case(self, source=None, arguments=()):
        with tempfile.TemporaryDirectory(prefix="h56-test-guard-") as scratch:
            root = Path(scratch)
            (root / "run_offline_tests.py").write_bytes(RUNNER.read_bytes())
            (root / "tests").mkdir()
            (root / "tests" / "__init__.py").write_bytes(b"")
            if source is not None:
                (root / "tests" / "test_control.py").write_bytes(source.encode("utf-8"))
            # No shell credentials or Python injection settings reach the child.
            environment = {name: os.environ[name] for name in
                           ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "COMSPEC")
                           if name in os.environ}
            child = subprocess.run(
                [sys.executable, "-B", "-E", "-S", str(root / "run_offline_tests.py")]
                + list(arguments), cwd=str(root), env=environment,
                capture_output=True, text=True, timeout=30)
            rows = [row.split("=", 1)[1] for row in child.stdout.splitlines()
                    if row.startswith("OFFLINE_TEST_SUMMARY=")]
            summary = json.loads(rows[0]) if len(rows) == 1 else None
            return child, summary

    def test_dns_tcp_udp_controls_are_blocked(self):
        child, summary = self.run_case(arguments=("--check-guard",))
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertIn("OFFLINE_GUARD_SELFTEST=PASS controls=4", child.stdout)
        self.assertEqual(summary["blocked_network_attempts"], 0)

    def test_normal_offline_test_still_passes(self):
        child, summary = self.run_case(
            "import unittest\nclass Control(unittest.TestCase):\n"
            "    def test_ok(self): self.assertEqual(2 + 2, 4)\n")
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(summary["tests_run"], 1)
        self.assertTrue(summary["tests_successful"])
        self.assertEqual(summary["blocked_network_attempts"], 0)

    def test_swallowed_network_error_fails_the_whole_run(self):
        child, summary = self.run_case(
            "import socket, unittest\nclass Control(unittest.TestCase):\n"
            "    def test_swallow(self):\n"
            "        try: socket.getaddrinfo('offline-guard.invalid', 443)\n"
            "        except RuntimeError: pass\n")
        self.assertEqual(child.returncode, 2, child.stderr)
        self.assertTrue(summary["tests_successful"])
        self.assertEqual(summary["blocked_events"], ["socket.getaddrinfo"])

    def test_import_time_network_is_also_blocked(self):
        child, summary = self.run_case(
            "import socket\nsocket.getaddrinfo('offline-guard.invalid', 443)\n")
        self.assertEqual(child.returncode, 2, child.stderr)
        self.assertFalse(summary["tests_successful"])
        self.assertEqual(summary["blocked_network_attempts"], 1)

    def test_accidentally_restored_live_transport_cannot_send_oauth(self):
        source = (
            "import os, sys, unittest\n"
            "sys.path.insert(0, %s)\n"
            "from app import sandbox\n"
            "os.environ['PAYPAL_CLIENT_ID'] = 'MOCK-CLIENT-ID-NOT-A-CREDENTIAL'\n"
            "os.environ['PAYPAL_CLIENT_SECRET'] = 'MOCK-SECRET-NOT-A-CREDENTIAL'\n"
            "class Control(unittest.TestCase):\n"
            "    def test_missing_mock(self):\n"
            "        client = sandbox.SandboxClient(sandbox.LiveTransport(sandbox.SANDBOX_BASE))\n"
            "        try: client.token()\n"
            "        except RuntimeError: pass\n"
        ) % json.dumps(str(RUNNER.parent))
        child, summary = self.run_case(source)
        self.assertEqual(child.returncode, 2, child.stderr)
        self.assertTrue(summary["tests_successful"])
        # Windows proxy discovery can resolve the local hostname first; both paths
        # must stop at DNS, before an OAuth HTTP request can leave the process.
        self.assertEqual(len(summary["blocked_events"]), 1)
        self.assertIn(summary["blocked_events"][0],
                      ("socket.getaddrinfo", "socket.gethostbyname"))
        self.assertNotIn("MOCK-SECRET-NOT-A-CREDENTIAL", child.stdout)

    def test_failure_without_network_is_not_reported_as_pass(self):
        child, summary = self.run_case(
            "import unittest\nclass Control(unittest.TestCase):\n"
            "    def test_bad(self): self.fail('offline failure control')\n")
        self.assertEqual(child.returncode, 1, child.stderr)
        self.assertFalse(summary["tests_successful"])
        self.assertEqual(summary["blocked_network_attempts"], 0)

    def test_empty_discovery_is_not_a_pass(self):
        child, summary = self.run_case()
        self.assertEqual(child.returncode, 1, child.stderr)
        self.assertEqual(summary["tests_run"], 0)

    def test_attempt_report_excludes_arguments(self):
        child, summary = self.run_case(
            "import sys, unittest\nclass Control(unittest.TestCase):\n"
            "    def test_private_arg(self):\n"
            "        try: sys.audit('socket.connect', None, 'PRIVATE-CONTROL-ARGUMENT')\n"
            "        except RuntimeError: pass\n")
        self.assertEqual(child.returncode, 2, child.stderr)
        self.assertNotIn("PRIVATE-CONTROL-ARGUMENT", child.stdout)
        self.assertEqual(summary["blocked_events"], ["socket.connect"])


if __name__ == "__main__":
    unittest.main()
