"""Static candidate-boundary audit for C2 source only."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "candidate_capability_feasibility_projection"
FORBIDDEN_IMPORTS = {"asyncio", "ctypes", "http", "importlib", "multiprocessing", "requests", "socket", "subprocess", "urllib"}
FORBIDDEN_CALLS = {"open", "popen", "run", "system", "Popen", "create_subprocess_exec", "create_subprocess_shell", "write_bytes", "write_text"}


def audit() -> list[str]:
    findings = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        findings.append("FORBIDDEN_IMPORT:%s:%s" % (path.name, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                findings.append("FORBIDDEN_IMPORT:%s:%s" % (path.name, node.module))
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                if name in FORBIDDEN_CALLS:
                    findings.append("FORBIDDEN_CALL:%s:%s" % (path.name, name))
    return findings


if __name__ == "__main__":
    findings = audit()
    if findings:
        print("\n".join(findings))
        raise SystemExit(2)
    print("PASS_CANDIDATE_CAPABILITY_FEASIBILITY_PROJECTION_BOUNDARY")
