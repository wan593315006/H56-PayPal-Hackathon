"""Path boundaries a string comparison cannot see.

`runs/` is not a location, it is a claim: everything this package writes stays inside the
package. A directory junction falsifies that claim while leaving every string comparison
intact — the junction is still named `runs`, still sits where `runs` sits, and still has
`runs/<name>` as a child. Measured on Python 3.9.13: `os.path.islink()` returns **False**
for a junction, so the symlink question cannot answer this one.

Both directions are tested, because guarding only creation lets a redirect that appears
later be accepted by recovery forever. The last case is the control: a plain directory must
still be accepted, or the guard would be "reject everything" and prove nothing.

Junctions are created with `mklink /J`, which needs no administrator rights. If the host
refuses, the case skips rather than fails: a missing privilege is not a passing guard.
Removal uses `os.rmdir` on the link itself — a recursive delete that follows a junction
would delete the target's contents.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import settings                                          # noqa: E402

STAMP = "20260101T000000Z"
NAME = STAMP + "_shop"


def junction(link, target):
    """Create a directory junction. Returns False when the host will not allow it."""
    finished = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                              capture_output=True, text=True)
    return finished.returncode == 0 and settings._reparse_point(Path(link))


class BoundaryTest(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="h56-boundary-")
        base = Path(self._scratch.name)
        self.package = base / "pkg"
        self.outside = base / "outside"
        self.package.mkdir()
        self.outside.mkdir()
        self._saved = (settings.RUNS_ROOT, settings.RECORDS_ROOT)
        settings.RUNS_ROOT = self.package / "runs"
        settings.RECORDS_ROOT = self.package / "records"

    def tearDown(self):
        settings.RUNS_ROOT, settings.RECORDS_ROOT = self._saved
        # Remove links first, with rmdir: a recursive delete that follows a junction
        # deletes what it points at, which here is the scratch "outside" tree.
        for candidate in (self.package / "runs" / NAME, self.package / "runs"):
            if os.path.lexists(str(candidate)) and settings._reparse_point(candidate):
                os.rmdir(str(candidate))
        self._scratch.cleanup()

    def test_junction_on_runs_blocks_creation(self):
        if not junction(settings.RUNS_ROOT, self.outside):
            self.skipTest("this host does not allow directory junctions")
        with self.assertRaises(settings.RunPathError) as caught:
            settings.run_directory(STAMP, "shop")
        self.assertEqual(caught.exception.code, "RUN_PATH_REPARSE_POINT")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_junction_on_runs_blocks_recovery(self):
        redirect = self.outside / NAME
        redirect.mkdir()
        (redirect / "result.json").write_text("{}", encoding="utf-8")
        if not junction(settings.RUNS_ROOT, self.outside):
            self.skipTest("this host does not allow directory junctions")
        # The bytes are really there through the redirect, which is exactly the danger.
        self.assertTrue((settings.RUNS_ROOT / NAME / "result.json").is_file())
        with self.assertRaises(settings.RunPathError) as caught:
            settings.existing_run_directory(STAMP, "shop")
        self.assertEqual(caught.exception.code, "RUN_PATH_REPARSE_POINT")

    def test_junction_on_the_run_directory_blocks_recovery(self):
        settings.RUNS_ROOT.mkdir()
        redirect = self.outside / NAME
        redirect.mkdir()
        if not junction(settings.RUNS_ROOT / NAME, redirect):
            self.skipTest("this host does not allow directory junctions")
        with self.assertRaises(settings.RunPathError) as caught:
            settings.existing_run_directory(STAMP, "shop")
        self.assertEqual(caught.exception.code, "RUN_PATH_REPARSE_POINT")
        # Creation is stopped for the same reason, and it says so: the name is taken
        # *by a redirect*, which is a different failure from "a real run got here first".
        with self.assertRaises(settings.RunPathError) as created:
            settings.run_directory(STAMP, "shop")
        self.assertEqual(created.exception.code, "RUN_PATH_REPARSE_POINT")

    def test_plain_directories_are_still_accepted(self):
        created = settings.run_directory(STAMP, "shop")
        self.assertEqual(created, settings.RUNS_ROOT / NAME)
        self.assertTrue(created.is_dir())
        self.assertEqual(settings.existing_run_directory(STAMP, "shop"), created)
        with self.assertRaises(settings.RunPathError) as again:
            settings.run_directory(STAMP, "shop")
        self.assertEqual(again.exception.code, "RUN_DIRECTORY_ALREADY_EXISTS")

    def test_escape_and_shape_controls_still_hold(self):
        for stamp, business, code in (
                ("2026-01-01T00:00:00Z", "shop", "STAMP_INVALID"),
                (STAMP, "../escape", "BUSINESS_INVALID"),
                (STAMP, "a/b", "BUSINESS_INVALID")):
            with self.assertRaises(settings.RunPathError) as caught:
                settings.run_directory(stamp, business)
            self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
