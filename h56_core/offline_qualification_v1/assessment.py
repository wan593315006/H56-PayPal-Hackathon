"""One synthetic evaluation or one explicit child; never dispatches tasks."""
from .contracts import (BOUNDARY, GRADE, SEMANTIC_FIELDS, Rejected, digest, need,
                        raw_sha, request, seal)
from .assets import load_assets, source_manifest
from .evidence import validate_evidence

class DiagnosticCommitFailure(Rejected):
    """Preserve native diagnostics when the private evidence commit also fails."""
    def __init__(self, native_diagnostic):
        super().__init__("ASSESSMENT_COMMIT_FAILED_WITH_NATIVE_DIAGNOSTIC", "RECORD")
        self.native_diagnostic = native_diagnostic

def check_parent(req, store):
    ref = req["parent_decision_ref"]
    if ref is None:
        return None
    old = store.view(ref)["record"]
    need(old["task_ref"] == req["task_ref"] and old["environment_id"] == req["environment_id"] and
         old["parent_decision_ref"] is None and
         old["source_binding"]["source_manifest_sha256"] == req["source_manifest_sha256"] and
         old["asset_binding"]["manifest_sha256"] == req["asset_manifest_sha256"],
         "ENV_PARENT_BINDING_MISMATCH")
    # A permits root -> one child only. No caller-supplied depth is trusted.
    return old

def evaluate(raw_evidence, req, store):
    need(type(raw_evidence) is bytes and len(raw_evidence) <= 262144, "INPUT_DATA_BUDGET")
    request(req, enforce_version=False)
    need(raw_sha(raw_evidence) == req["raw_evidence_sha256"], "ENV_INPUT_HASH_MISMATCH")
    store.check_conflict(req)
    request(req)
    product, source = source_manifest(req["source_manifest_sha256"])
    assets = load_assets(req["asset_manifest_sha256"])
    validated = validate_evidence(raw_evidence, req["raw_evidence_sha256"], req)
    check_parent(req, store)
    claim, committed = store.reserve(req)
    if committed is not None:
        return committed       # Return original; not a fresh computation.
    core = {name: None for name in SEMANTIC_FIELDS}
    core.update(schema="H56_OFFLINE_ASSESSMENT_RECORD_V1",
        assessment_id=claim["assessment_id"], parent_decision_ref=req["parent_decision_ref"],
        task_ref=req["task_ref"], environment_id=req["environment_id"], evidence_grade=GRADE,
        raw_evidence_sha256=req["raw_evidence_sha256"], as_of=req["as_of"],
        source_validation=dict(status="SOURCE_BYTES_VERIFIED_SYNTHETIC_ONLY",
                               external_fact_trust=False, execution_authority=False),
        source_binding=dict(source_manifest_sha256=req["source_manifest_sha256"],
            interface_version=req["interface_version"],
            core_commit="9221e16460258bc81e1176d69f63a09f81159b73"),
        asset_binding=dict(manifest_sha256=req["asset_manifest_sha256"], hashes=assets["hashes"]),
        admission_candidate="NO_DECISION", reason_codes=validated["reason_codes"],
        required_evidence=validated["required_evidence"], boundary=dict(BOUNDARY),
        stage="SOURCE", failure=None)
    # First original-core import and every core operation occur after reserve.
    from .core_bridge import NativeFailure, compute
    diagnostic = None
    try:
        outputs = compute(validated, assets, req, product)
    except NativeFailure as exc:
        diagnostic = exc.raw_diagnostic
        outputs = exc.outputs
        for name in core:
            if name in outputs:
                core[name] = outputs[name]
        core.update(stage=exc.stage, failure=dict(code=exc.code, exception_type=exc.exception_type,
                                                cause_code=exc.cause_code),
                    admission_candidate="NO_DECISION", c2_projection=None,
                    reason_codes=list(dict.fromkeys(validated["reason_codes"] + [exc.code])))
        if core["mapping_trace"] is None:
            core["mapping_trace"] = dict(native_calls=outputs.get("native_calls", []))
    else:
        for name in core:
            if name in outputs:
                core[name] = outputs[name]
    result = seal(core)
    # Failure records describe failure only; durable commit never grants permission.
    try:
        committed = store.commit(result, claim)
    except Exception as exc:
        if diagnostic is not None:
            # The original failure is separate from the persistence failure.
            # Neither raw diagnostic becomes a semantic result or permission.
            raise DiagnosticCommitFailure(diagnostic) from exc
        raise
    if diagnostic is not None:
        committed["transport_diagnostic"] = diagnostic  # Not part of record/hash.
    return committed

def request_reassessment(old_reference, raw_evidence, req, store):
    need(req["parent_decision_ref"] == old_reference, "ENV_PARENT_BINDING_MISMATCH")
    return evaluate(raw_evidence, req, store)
