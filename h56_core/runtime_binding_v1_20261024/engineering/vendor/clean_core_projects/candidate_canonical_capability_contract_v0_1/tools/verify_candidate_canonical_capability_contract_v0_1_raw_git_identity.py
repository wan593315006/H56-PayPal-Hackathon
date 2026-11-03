"""Compare every C1 manifest source byte-for-byte with one frozen Git commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
MANIFEST = ROOT / "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_MANIFEST.json"
PROJECT_PREFIX = "clean_core_projects/candidate_canonical_capability_contract_v0_1/"


def git_show(commit: str, repository_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", "%s:%s" % (commit, repository_path)],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise SystemExit("RAW_GIT_SOURCE_UNAVAILABLE:%s" % repository_path)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["source_files"]:
        local = ROOT / entry["path"]
        repository_path = PROJECT_PREFIX + entry["path"]
        if not local.is_file() or local.read_bytes() != git_show(args.commit, repository_path):
            print("RAW_GIT_IDENTITY_MISMATCH:%s" % entry["path"])
            return 2
    print("PASS_C1_RAW_GIT_IDENTITY:%s:%d" % (args.commit, len(manifest["source_files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
