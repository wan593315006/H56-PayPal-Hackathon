"""Build the derived, source-hash project manifest for C1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_MANIFEST.json"
FILES = (
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_REQUIREMENT.md",
    "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_PROJECT_CARD.md",
    "C1_C0_AUDIT_BINDING_V1.json",
    "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1_STRUCTURED_SEMANTIC_REVIEW_INPUT_V1.json",
    "src/candidate_canonical_capability_contract/__init__.py",
    "src/candidate_canonical_capability_contract/contracts.py",
    "src/candidate_canonical_capability_contract/catalog.py",
    "tests/test_candidate_canonical_capability_contract_v0_1.py",
    "tools/audit_candidate_canonical_capability_contract_v0_1_boundary.py",
    "tools/verify_c0_unified_capability_pool_audit_binding.py",
    "tools/build_candidate_canonical_capability_contract_v0_1_manifest.py",
    "tools/verify_candidate_canonical_capability_contract_v0_1_manifest.py",
    "tools/verify_candidate_canonical_capability_contract_v0_1_raw_git_identity.py",
    "tools/review_with_five_body.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    source_files = []
    for relative in FILES:
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit("MISSING_MANIFEST_SOURCE:%s" % relative)
        source_files.append({"path": relative.replace("\\", "/"), "sha256": digest(path)})
    return {
        "schema_version": "1.0.0",
        "project_id": "CANDIDATE_CANONICAL_CAPABILITY_CONTRACT_V0_1",
        "status": "CANDIDATE_ONLY",
        "source_files": source_files,
        "boundaries": {
            "capability_availability": False,
            "agent_creation_or_coordination": False,
            "authority_or_commit_creation": False,
            "history_state_runtime_formal_mlm_write": False,
            "network_mcp_provider_bus_pipeline": False,
            "tool_or_external_execution": False,
            "legacy_import_or_call": False,
        },
    }


if __name__ == "__main__":
    manifest = build()
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BUILT_C1_PROJECT_MANIFEST:%d" % len(manifest["source_files"]))
