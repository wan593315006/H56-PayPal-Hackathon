"""Synthetic evidence adaptation; never reads live host properties."""
from .contracts import (FIELDS, GRADE, ROLE, decode, exact, need, raw_sha,
                        stamp, task, token)

ENVELOPE_KEYS = ("schema", "evidence_set_id", "evidence_grade", "source_id",
    "source_version", "environment_id", "environment_role", "task_ref", "items")
ITEM_KEYS = ("evidence_id", "field", "knowledge", "value", "source_id",
             "observed_at", "coverage")

def validate_evidence(raw_bytes, expected_raw_sha256, execution_binding):
    need(type(raw_bytes) is bytes and len(raw_bytes) <= 262144, "INPUT_DATA_BUDGET")
    need(raw_sha(raw_bytes) == expected_raw_sha256, "ENV_INPUT_HASH_MISMATCH")
    value = decode(raw_bytes)
    exact(value, ENVELOPE_KEYS)
    need(value["schema"] == "H56_ENV_EVIDENCE_V1" and
         value["source_version"] == "1.0.0", "ENV_SOURCE_OR_VERSION_MISMATCH")
    need(value["evidence_grade"] == GRADE and value["source_id"] == "SYNTHETIC_FIXTURE_V1",
         "ENV_SOURCE_GRADE_MISMATCH")
    token(value["evidence_set_id"]); token(value["environment_id"]); task(value["task_ref"])
    need(value["environment_role"] == ROLE and
         value["environment_id"] == execution_binding["environment_id"] and
         value["task_ref"] == execution_binding["task_ref"], "ENV_TASK_SCOPE_MISMATCH")
    as_of = stamp(execution_binding["as_of"])
    need(type(value["items"]) is list and len(value["items"]) <= 16, "INPUT_DATA_BUDGET")
    ids, seen, normalized, reasons, required = set(), set(), {}, [], []
    observed = []
    for item in value["items"]:
        exact(item, ITEM_KEYS); token(item["evidence_id"])
        name = item["field"]
        need(name in FIELDS, "ENV_INPUT_REJECTED")
        need(name not in seen and item["evidence_id"] not in ids, "ENV_EVIDENCE_CONFLICT")
        seen.add(name); ids.add(item["evidence_id"])
        need(item["source_id"] == value["source_id"], "ENV_SOURCE_GRADE_MISMATCH")
        known = item["knowledge"]
        need(known in ("KNOWN", "UNKNOWN"), "ENV_INPUT_REJECTED")
        v = item["value"]
        need((known == "UNKNOWN" and v is None) or (known == "KNOWN" and v is not None),
             "ENV_INPUT_REJECTED")
        if v is not None:
            if name == "integrity_rid":
                need(type(v) is int and v in (0, 4096, 8192, 12288, 16384), "ENV_INPUT_REJECTED")
            else:
                need(type(v) is bool, "ENV_INPUT_REJECTED")
        need(item["coverage"] in ("FIELD_ONLY", "FULL_ANCESTOR_CHAIN", "IMMEDIATE_JOB_ONLY"),
             "ENV_INPUT_REJECTED")
        when = stamp(item["observed_at"]); observed.append(item["observed_at"])
        age = int((as_of - when).total_seconds())
        need(age >= 0, "ENV_TIME_INVALID_OR_FUTURE")
        issues = []
        if age > 300:
            issues.append("ENV_EVIDENCE_EXPIRED")
        if name == "outer_job_clear" and item["coverage"] != "FULL_ANCESTOR_CHAIN":
            issues.append("ENV_OUTER_JOB_SCOPE_INCOMPLETE")
        effective = v if known == "KNOWN" and not issues else None
        if effective is None:
            required.append(name)
            if not issues:
                issues.append("ENV_EVIDENCE_MISSING")
        normalized[name] = dict(value=effective, original=item, age_seconds=age, reasons=issues)
    for name in FIELDS:
        if name not in normalized:
            normalized[name] = dict(value=None, original=None, age_seconds=None,
                                    reasons=["ENV_EVIDENCE_MISSING"])
            required.append(name)
        reasons.extend(normalized[name]["reasons"])
    state = {name: normalized[name]["value"] for name in FIELDS}
    if state["app_container"] is True:
        reasons.append("ENV_APPCONTAINER_NOT_ALLOWED_FOR_ROLE")
    if state["integrity_rid"] is not None and state["integrity_rid"] not in (8192, 12288, 16384):
        reasons.append("ENV_INTEGRITY_BELOW_REQUIRED")
    for field, reason in (("host_directory_normal", "ENV_HOST_DIRECTORY_REDIRECTED"),
                          ("dependencies_available", "ENV_DEPENDENCY_UNAVAILABLE")):
        if state[field] is False:
            reasons.append(reason)
    need_evidence = [name for name in FIELDS if normalized[name]["value"] is None]
    if state["supporting_attestation"] is not True:
        need_evidence.append("supporting_attestation")
    return dict(envelope=value, normalized_evidence=normalized, state_projection=state,
                occurred_at=max(observed) if observed else execution_binding["as_of"],
                occurred_at_derivation="MAX_OBSERVED_AT" if observed else "EXPLICIT_AS_OF_NO_ITEMS",
                evidence_state="SUFFICIENT" if not need_evidence else "INSUFFICIENT",
                reason_codes=list(dict.fromkeys(reasons)),
                required_evidence=list(dict.fromkeys(need_evidence)))
