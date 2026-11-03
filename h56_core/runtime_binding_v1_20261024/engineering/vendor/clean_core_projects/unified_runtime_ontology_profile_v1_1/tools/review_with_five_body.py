"""Create a source-hash-bound structured candidate semantic-review receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT.parent / "candidate_semantic_review_quality_gate_v1" / "src"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output != ROOT.resolve() and ROOT.resolve() not in output.parents:
        raise SystemExit("OUTPUT_MUST_REMAIN_INSIDE_PROJECT")
    sys.path.insert(0, str(GATE))
    from candidate_semantic_review_quality_gate import evaluate_candidate_review

    requirement = ROOT / "UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_REQUIREMENT.md"
    structured = ROOT / "UNIFIED_RUNTIME_ONTOLOGY_PROFILE_V1_1_STRUCTURED_SEMANTIC_REVIEW_INPUT_V1.json"
    receipt = {
        "review_id": "FIVE_BODY_STRUCTURED_CANDIDATE_REVIEW:UNIFIED_RUNTIME_ONTOLOGY_PROFILE:V1_1",
        "source_bound_inputs": {
            "requirement_sha256": hashlib.sha256(requirement.read_bytes()).hexdigest(),
            "structured_input_sha256": hashlib.sha256(structured.read_bytes()).hexdigest(),
        },
        "semantic_quality_gate": evaluate_candidate_review(json.loads(structured.read_text(encoding="utf-8"))),
        "boundary": {
            "candidate_only": True,
            "ontology_runtime_or_registry": False,
            "state_history_runtime_formal_mlm_write": False,
            "legacy_import_or_call": False,
            "authority_commit_policy_execution": False,
            "network_mcp_provider_bus_pipeline": False,
            "tool_or_external_execution": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = receipt["semantic_quality_gate"]
    print(json.dumps({"status": result["status"], "issues": result["issue_count"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
