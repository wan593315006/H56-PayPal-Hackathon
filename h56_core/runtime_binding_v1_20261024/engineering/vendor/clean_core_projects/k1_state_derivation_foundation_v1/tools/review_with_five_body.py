"""Opt-in candidate-only Five-Body semantic/software-world review for K1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_GATE_ROOT = PROJECT_ROOT.parent / "candidate_semantic_review_quality_gate_v1"

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-workbench-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    workbench = args.legacy_workbench_root.resolve()
    requirement = PROJECT_ROOT / "K1_REQUIREMENT.md"
    review_input = PROJECT_ROOT / "K1_CANDIDATE_REVIEW_INPUT.md"
    profile_path = SHARED_GATE_ROOT / "CANONICAL_KERNEL_REVIEW_PROFILE_V1.json"
    business_compiler = workbench / "five_body_engineering_lab" / "business_semantic_compiler.py"
    software_compiler = workbench / "five_body_engineering_lab" / "software_world_model_compiler.py"
    if not business_compiler.is_file() or not software_compiler.is_file():
        raise SystemExit("explicit workbench root does not expose safe candidate compilers")
    sys.path.insert(0, str(workbench))
    sys.path.insert(0, str(SHARED_GATE_ROOT / "src"))
    from five_body_engineering_lab import BusinessSemanticCompiler, SoftwareWorldModelCompiler
    from candidate_semantic_review_quality_gate import evaluate_candidate_review

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    semantic = BusinessSemanticCompiler(
        domain_profiles={profile["domain_hint"]: profile}
    ).compile(
        review_input.read_text(encoding="utf-8"),
        model_id="BIZ:K1:STATE_DERIVATION:V1",
        domain_hint=profile["domain_hint"],
        evidence_refs=["K1_CANDIDATE_REVIEW_INPUT"],
    ).semantic_model
    reviewed = SoftwareWorldModelCompiler().compile(
        semantic,
        model_id="SW:K1:STATE_DERIVATION:V1",
    )
    payload: dict[str, Any] = {
        "review_id": "FIVE_BODY_CANDIDATE_REVIEW:K1:V1",
        "source_bound_inputs": {
            "k1_requirement_sha256": _sha256(requirement),
            "controlled_review_input_sha256": _sha256(review_input),
            "controlled_review_profile_sha256": _sha256(profile_path),
            "business_semantic_compiler_sha256": _sha256(business_compiler),
            "software_world_model_compiler_sha256": _sha256(software_compiler),
            "quality_gate_sha256": _sha256(
                SHARED_GATE_ROOT / "src" / "candidate_semantic_review_quality_gate" / "quality_gate.py"
            ),
        },
        "candidate_review": reviewed.to_dict(),
        "semantic_quality_gate": evaluate_candidate_review(reviewed.to_dict()),
        "boundary": {
            "candidate_only": True,
            "runtime_authority": "not_authorized",
            "formal_mlm_write": False,
            "legacy_source_write": False,
            "provider_or_mcp_call": False,
            "external_side_effect": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload["semantic_quality_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
