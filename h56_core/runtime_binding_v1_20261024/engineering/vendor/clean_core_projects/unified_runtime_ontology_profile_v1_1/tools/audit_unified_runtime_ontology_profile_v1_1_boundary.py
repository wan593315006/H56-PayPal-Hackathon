#!/usr/bin/env python3
"""Static no-effect boundary scan for the candidate ontology profile."""
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
FORBIDDEN = (
    "import socket",
    "import subprocess",
    "import requests",
    "import urllib",
    "import sqlite3",
    "importlib",
    "os.system(",
    "Popen(",
    "run(",
    "wuti_bus",
    "mcp",
    "provider",
    "pipeline",
    "legacy",
    "history.append",
    "state.write",
)


def main() -> int:
    failures = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                failures.append("%s:%s" % (path.relative_to(PROJECT_ROOT), token))
    if failures:
        print("FAIL_UNIFIED_RUNTIME_ONTOLOGY_PROFILE_BOUNDARY")
        print("\n".join(failures))
        return 1
    print("PASS_UNIFIED_RUNTIME_ONTOLOGY_PROFILE_BOUNDARY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
