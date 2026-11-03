"""Opt-in, no-side-effect candidate review using existing Five-Body compilers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_GATE_ROOT = PROJECT_ROOT.parent / "candidate_semantic_review_quality_gate_v1"

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-workbench-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    workbench = args.legacy_workbench_root.resolve()
    requirement = PROJECT_ROOT / "K0_REQUIREMENT.md"
    review_input = PROJECT_ROOT / "K0_CANDIDATE_REVIEW_INPUT.md"
    profile_path = SHARED_GATE_ROOT / "CANONICAL_KERNEL_REVIEW_PROFILE_V1.json"
    compiler_path = workbench / "five_body_engineering_lab" / "business_semantic_compiler.py"
    software_world_path = workbench / "five_body_engineering_lab" / "software_world_model_compiler.py"
    if not compiler_path.is_file() or not software_world_path.is_file():
        raise SystemExit("explicit legacy workbench root does not expose the candidate compilers")

    sys.path.insert(0, str(workbench))
    sys.path.insert(0, str(SHARED_GATE_ROOT / "src"))
    from five_body_engineering_lab import BusinessSemanticCompiler, SoftwareWorldModelCompiler
    from candidate_semantic_review_quality_gate import evaluate_candidate_review

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    semantic_result = BusinessSemanticCompiler(
        domain_profiles={profile["domain_hint"]: profile}
    ).compile(
        review_input.read_text(encoding="utf-8"),
        model_id="BIZ:K0:CANONICAL_FACT_FOUNDATION:V1",
        domain_hint=profile["domain_hint"],
        evidence_refs=["K0_CANDIDATE_REVIEW_INPUT"],
    )
    software_result = SoftwareWorldModelCompiler().compile(
        semantic_result.semantic_model,
        model_id="SW:K0:CANONICAL_FACT_FOUNDATION:V1",
    )
    report: dict[str, Any] = {
        "review_id": "FIVE_BODY_CANDIDATE_REVIEW:K0:V1",
        "source_bound_inputs": {
            "k0_requirement_sha256": sha256(requirement),
            "controlled_review_input_sha256": sha256(review_input),
            "controlled_review_profile_sha256": sha256(profile_path),
            "business_semantic_compiler_sha256": sha256(compiler_path),
            "software_world_model_compiler_sha256": sha256(software_world_path),
            "quality_gate_sha256": sha256(
                SHARED_GATE_ROOT / "src" / "candidate_semantic_review_quality_gate" / "quality_gate.py"
            ),
        },
        "candidate_review": software_result.to_dict(),
        "semantic_quality_gate": evaluate_candidate_review(software_result.to_dict()),
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
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["semantic_quality_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
