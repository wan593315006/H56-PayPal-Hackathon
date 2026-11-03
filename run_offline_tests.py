"""Run the package tests with a fail-closed Python network guard.

The guard is installed before discovery/import. A swallowed network exception still
fails the run. It lives until this interpreter exits; there is no live-mode switch.
This is a Python-process regression guard, not an OS firewall or a child-process sandbox.
"""
import argparse
import json
import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLOCKED_EVENTS = frozenset((
    "socket.connect", "socket.sendto", "socket.sendmsg",
    "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
))


class OfflineNetworkBlocked(RuntimeError):
    pass


class NetworkGuard:
    def __init__(self):
        self.events = []

    def audit(self, event, _args):
        if event in BLOCKED_EVENTS:
            # Do not retain arguments: a URL, header or payload can contain a secret.
            self.events.append(event)
            raise OfflineNetworkBlocked("OFFLINE_NETWORK_BLOCKED:" + event)

    def install(self):
        sys.addaudithook(self.audit)

    def selfcheck(self):
        """Check the hook before touching socket APIs, then check DNS/TCP/UDP APIs."""
        start = len(self.events)
        try:
            sys.audit("socket.connect", None, ("127.0.0.1", 9))
        except OfflineNetworkBlocked:
            pass
        else:
            raise RuntimeError("OFFLINE_NETWORK_GUARD_NOT_INSTALLED")

        probes = (
            ("socket.getaddrinfo", lambda: socket.getaddrinfo("offline-guard.invalid", 443)),
            ("socket.connect", self._tcp_probe),
            ("socket.sendto", self._udp_probe),
        )
        for expected, call in probes:
            before = len(self.events)
            try:
                call()
            except OfflineNetworkBlocked:
                pass
            else:
                raise RuntimeError("OFFLINE_NETWORK_GUARD_PROBE_FAILED:" + expected)
            if self.events[before:] != [expected]:
                raise RuntimeError("OFFLINE_NETWORK_GUARD_EVENT_MISMATCH")
        return len(self.events) - start

    @staticmethod
    def _tcp_probe():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
            stream.connect(("127.0.0.1", 9))

    @staticmethod
    def _udp_probe():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as stream:
            stream.sendto(b"offline-guard-control", ("127.0.0.1", 9))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--pattern", default="test_*.py")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--check-guard", action="store_true",
                        help="verify the guard only, without discovering tests")
    args = parser.parse_args(argv)
    # A filename glob only: selecting files must not change the test root.
    if any(separator in args.pattern for separator in ("/", "\\")):
        parser.error("--pattern must be a filename glob")

    guard = NetworkGuard()
    guard.install()
    try:
        controls = guard.selfcheck()
    except Exception as error:
        print("OFFLINE_GUARD_SELFTEST=FAIL " + type(error).__name__)
        return 2
    print("OFFLINE_GUARD_SELFTEST=PASS controls=%d" % controls, flush=True)
    # Keep selfcheck events, but report them separately from actual test attempts.
    first_test_event = len(guard.events)
    successful, count = True, 0
    if not args.check_guard:
        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), pattern=args.pattern, top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
        count, successful = result.testsRun, result.wasSuccessful()
        if count == 0:
            successful = False

    attempts = guard.events[first_test_event:]
    print("OFFLINE_TEST_SUMMARY=" + json.dumps({
        "tests_run": count,
        "tests_successful": successful,
        "blocked_network_attempts": len(attempts),
        "blocked_events": attempts,
    }, sort_keys=True))
    # Even a test which caught and swallowed OfflineNetworkBlocked cannot make this PASS.
    status = 2 if attempts else (0 if successful else 1)
    print("OFFLINE_TEST_EXIT=%d" % status)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
