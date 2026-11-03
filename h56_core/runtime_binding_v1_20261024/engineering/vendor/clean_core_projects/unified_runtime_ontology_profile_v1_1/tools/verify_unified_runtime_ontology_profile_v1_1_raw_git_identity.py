#!/usr/bin/env python3
"""Replay the project manifest from raw Git bytes at an explicit commit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
PROJECT_RELATIVE = PROJECT_ROOT.relative_to(REPO_ROOT).as_posix()


def git_bytes(commit: str, relative_path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(REPO_ROOT), "show", "%s:%s/%s" % (commit, PROJECT_RELATIVE, relative_path)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        manifest_bytes = git_bytes(args.commit, "UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_MANIFEST.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        failures = []
        for item in manifest["managed_files"]:
            actual = hashlib.sha256(git_bytes(args.commit, item["path"])).hexdigest()
            if actual != item["sha256"]:
                failures.append(item["path"])
    except (subprocess.CalledProcessError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("FAIL_URO_V1_1_RAW_GIT_IDENTITY:%s" % exc)
        return 1
    if failures:
        print("FAIL_URO_V1_1_RAW_GIT_IDENTITY_HASH:%s" % ",".join(failures))
        return 1
    print("PASS_URO_V1_1_RAW_GIT_IDENTITY:%s:%d" % (args.commit, len(manifest["managed_files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
