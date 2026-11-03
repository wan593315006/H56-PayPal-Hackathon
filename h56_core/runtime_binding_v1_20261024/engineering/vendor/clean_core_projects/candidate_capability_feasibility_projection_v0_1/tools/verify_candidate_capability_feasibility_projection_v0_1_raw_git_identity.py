"""Compare every C2 manifest file with one frozen Git commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
MANIFEST = ROOT / "CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_V0_1_PROJECT_MANIFEST.json"
PREFIX = "clean_core_projects/candidate_capability_feasibility_projection_v0_1/"


def show(commit: str, repository_path: str) -> bytes:
    result = subprocess.run(["git", "show", "%s:%s" % (commit, repository_path)], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode:
        raise SystemExit("RAW_GIT_SOURCE_UNAVAILABLE:%s" % repository_path)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for item in value["source_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or path.read_bytes() != show(args.commit, PREFIX + item["path"]):
            print("RAW_GIT_IDENTITY_MISMATCH:%s" % item["path"])
            return 2
    print("PASS_C2_RAW_GIT_IDENTITY:%s:%d" % (args.commit, len(value["source_files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
