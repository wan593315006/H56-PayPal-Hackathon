"""Entry point: `python -B -m app.main selfcheck`.

selfcheck answers one question — is this directory the package that was assembled? —
and answers it from bytes, not from a version string. Each check prints one line with
the measured value, so a failure says what it saw rather than that something is wrong.
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import settings

LONG_PREFIX = "\\\\?\\"
EXPECTED_EXPORTS = ("Assertion", "Catalog", "Compiler", "Context", "Definition",
                    "Evaluator", "Fact", "History", "Provenance", "Reference",
                    "StateCompilationError", "VersionTuple", "native_hash")
COLD_START = """
import json
import sys
from pathlib import Path

core = Path(sys.argv[1])
sys.path.insert(0, str(core))
from offline_qualification_v1.core_bridge import load_core

native, receipt = load_core(core, sys.argv[2])
print(json.dumps({"exports": sorted(native), "receipt": receipt}, sort_keys=True))
"""


class SelfcheckError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def _long(path):
    text = str(path)
    return text if text.startswith(LONG_PREFIX) else LONG_PREFIX + text


def _walk_files(root):
    """Yield (posix relative path, long absolute path) for every file under root."""
    prefix = _long(root) + os.sep
    for base, _dirs, files in os.walk(prefix):
        for name in files:
            full = os.path.join(base, name)
            yield full[len(prefix):].replace(os.sep, "/"), full


def _read_manifest():
    """Read the shipped declaration without trusting it: hash first, then parse."""
    path = _long(settings.CORE_ROOT / settings.DECLARATION_PATH)
    with open(path, "rb") as handle:
        raw = handle.read()
    measured = hashlib.sha256(raw).hexdigest()
    if measured != settings.SOURCE_MANIFEST_SHA:
        raise SelfcheckError("SOURCE_MANIFEST_SHA", measured)
    document = json.loads(raw.decode("utf-8"))
    members = document.get("runtime_required")
    if not isinstance(members, list) or len(members) != settings.MEMBER_COUNT:
        raise SelfcheckError("SOURCE_MEMBER_COUNT", len(members or []))
    return members, len(raw)


def check_disk_set(members):
    """C1: the disk holds the 139 members plus the declaration, and nothing else."""
    expected = {m["path"] for m in members} | {settings.DECLARATION_PATH}
    actual = {rel for rel, _ in _walk_files(settings.CORE_ROOT)}
    extra, missing = sorted(actual - expected), sorted(expected - actual)
    detail = "files=%d expected=%d" % (len(actual), len(expected))
    if extra:
        detail += " extra=" + ",".join(extra[:3])
    if missing:
        detail += " missing=" + ",".join(missing[:3])
    return (not extra and not missing), detail


def check_source_identity():
    """C2: the kernel's own reader agrees on the product root and the 139 count."""
    from offline_qualification_v1.assets import source_manifest

    product, document = source_manifest(settings.SOURCE_MANIFEST_SHA)
    same_root = os.path.normcase(str(Path(product))) == os.path.normcase(str(settings.CORE_ROOT))
    count = len(document["runtime_required"])
    return (same_root and count == settings.MEMBER_COUNT), \
        "root_matches=%s members=%d" % (same_root, count)


def check_assets():
    """C3: the three fixed assets load, hash-check and satisfy their field contracts."""
    from offline_qualification_v1.assets import load_assets

    assets = load_assets(settings.ASSET_MANIFEST_SHA)
    names = sorted(k for k in assets if k in ("policy", "mapping", "capability"))
    role = assets["policy"]["role"]
    return (names == ["capability", "mapping", "policy"] and role == "SIMULATED_OPERATOR_METADATA_HOST"), \
        "assets=%s role=%s" % (",".join(names), role)


def check_tests():
    """C4: the 30 offline cases pass, with a scratch root created outside the package."""
    from offline_qualification_v1.tests import test_records

    previous = test_records.TEST_ROOT
    with tempfile.TemporaryDirectory(prefix="h56-selfcheck-") as scratch:
        test_records.TEST_ROOT = scratch
        try:
            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            for name in settings.TEST_MODULES:
                suite.addTests(loader.loadTestsFromName("offline_qualification_v1.tests." + name))
            cases = suite.countTestCases()
            stream = io.StringIO()
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
        finally:
            test_records.TEST_ROOT = previous
    ok = cases == 30 and not result.failures and not result.errors
    detail = "cases=%d failures=%d errors=%d skipped=%d" % (
        cases, len(result.failures), len(result.errors), len(result.skipped))
    if not ok:
        first = (result.failures + result.errors)
        if first:
            detail += " first=" + first[0][0].id().rsplit(".", 1)[-1]
    return ok, detail


def check_cold_start():
    """C5: a fresh interpreter imports the four native cores from pinned source bytes.

    Run in a child process so the result does not depend on what the test suite already
    imported. The child gets `-E` (no Python environment configuration), `-B` (no byte
    cache) and an allowlisted environment: inheriting the parent's environment would hand
    it credentials it has no use for.
    """
    environment = settings.subprocess_environment()
    finished = subprocess.run(
        [sys.executable, "-B", "-E", "-c", COLD_START,
         str(settings.CORE_ROOT), settings.SOURCE_MANIFEST_SHA],
        cwd=str(settings.PACKAGE_ROOT), env=environment, capture_output=True, text=True)
    if finished.returncode != 0:
        tail = (finished.stderr or "").strip().splitlines()
        raise SelfcheckError("NATIVE_COLD_START_FAILED", tail[-1][:200] if tail else "no stderr")
    line = [row for row in (finished.stdout or "").splitlines() if row.strip()][-1]
    payload = json.loads(line)
    exports = tuple(payload["exports"])
    receipt = payload["receipt"]
    ok = (exports == EXPECTED_EXPORTS and receipt["file_count"] == 110
          and receipt["source_commit"] == "9221e16460258bc81e1176d69f63a09f81159b73"
          and receipt["status"] == "SOURCE_IDENTITY_ONLY")
    return ok, "exports=%d vendor_files=%d commit=%s env_keys=%d" % (
        len(exports), receipt["file_count"], receipt["source_commit"][:8], len(environment))


def check_clean():
    """C6: running everything above left no byte cache behind."""
    caches = files = 0
    for rel, _full in _walk_files(settings.CORE_ROOT):
        parts = rel.split("/")
        if "__pycache__" in parts:
            caches += 1
        elif rel.endswith(".pyc"):
            files += 1
    return (caches == 0 and files == 0), "pycache=%d pyc=%d" % (caches, files)


CHECKS = (
    ("C1", "disk file set", check_disk_set),
    ("C2", "source identity", check_source_identity),
    ("C3", "fixed assets", check_assets),
    ("C4", "offline cases", check_tests),
    ("C5", "native cold start", check_cold_start),
    ("C6", "no byte cache", check_clean),
)


def selfcheck():
    members, declaration_bytes = _read_manifest()
    total = sum(m["size"] for m in members)
    print("package   %s" % settings.PACKAGE_ROOT)
    print("python    %s" % sys.version.split()[0])
    print("members   %d (%d B) + declaration %d B" % (
        len(members), total, declaration_bytes))
    print("-" * 62)
    sys.path.insert(0, str(settings.CORE_ROOT))
    # C1 is the only check that needs the parsed member list; bind it here so the rest of
    # the table stays a plain list of zero-argument callables.
    checks = [("C1", "disk file set", lambda: check_disk_set(members))]
    checks.extend(row for row in CHECKS if row[0] != "C1")
    passed = 0
    for code, label, check in checks:
        try:
            ok, detail = check()
        except SelfcheckError as error:
            ok, detail = False, "%s %s" % (error.code, error)
        except Exception as error:  # a raised error is a failed check, not a crash
            ok, detail = False, "%s: %s" % (type(error).__name__, str(error)[:160])
        passed += 1 if ok else 0
        print("%-4s %-3s %-18s %s" % ("PASS" if ok else "FAIL", code, label, detail))
    print("-" * 62)
    if passed == len(checks):
        print("SELFCHECK PASS %d/%d" % (passed, len(checks)))
        return 0
    print("SELFCHECK FAIL %d/%d" % (passed, len(checks)))
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="app.main", description="H56 PayPal submission package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selfcheck", help="verify the package against its own identity record")
    arguments = parser.parse_args(argv)
    if arguments.command == "selfcheck":
        return selfcheck()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
