"""Core-free source tests. NOT EXECUTED in A-S."""
import copy
import json
import unittest
from pathlib import Path
from offline_qualification_v1.contracts import canonical, decode, digest, raw_sha, request, Rejected
from offline_qualification_v1.evidence import validate_evidence

def fixture():
    # Negative test descriptors intentionally include invalid numeric values.
    return json.loads((Path(__file__).absolute().parents[1] / "fixtures" / "cases.json").read_text(encoding="utf-8"))

def case_envelope(case_id="C01", variant=0):
    data = fixture()
    env = copy.deepcopy(data["base_envelope"])
    selected = next(c for c in data["cases"] if c["id"] == case_id)["variants"][variant]
    env.update(selected.get("envelope", {}))
    for item in list(env["items"]):
        field = item["field"]
        if field in selected.get("remove", []):
            env["items"].remove(item)
            continue
        if field in selected.get("fields", {}):
            item["value"] = selected["fields"][field]
        if field in selected.get("unknown", []):
            item.update(knowledge="UNKNOWN", value=None)
        if field in selected.get("knowledge_value", {}):
            item.update(selected["knowledge_value"][field])
        for source, target in (("observed_at", "observed_at"), ("coverage", "coverage")):
            if field in selected.get(source, {}):
                item[target] = selected[source][field]
    if selected.get("duplicate_field") or selected.get("conflicting_field"):
        duplicate = copy.deepcopy(env["items"][0])
        duplicate["evidence_id"] = "duplicate_field_item"
        if selected.get("conflicting_field"):
            duplicate["value"] = not duplicate["value"]
        env["items"].append(duplicate)
    if selected.get("duplicate_id"):
        env["items"][1]["evidence_id"] = env["items"][0]["evidence_id"]
    if selected.get("strict_type_field") == "integrity_rid":
        next(i for i in env["items"] if i["field"] == "integrity_rid")["value"] = selected["invalid_value"]
    return env

def evidence_bytes(env):
    return canonical(env).encode("utf-8")

def metadata(env, request_id="request_1"):
    return dict(schema="H56_OFFLINE_ASSESSMENT_REQUEST_V1", request_id=request_id,
        task_ref=copy.deepcopy(fixture()["base_envelope"]["task_ref"]),
        environment_id="synthetic_env", raw_evidence_sha256=raw_sha(evidence_bytes(env)),
        as_of=fixture()["base_as_of"], source_manifest_sha256="0"*64,
        asset_manifest_sha256="0"*64, interface_version="1.0.0", parent_decision_ref=None)

def validated(case_id="C01", variant=0):
    env = case_envelope(case_id, variant)
    req = metadata(env)
    return validate_evidence(evidence_bytes(env), req["raw_evidence_sha256"], req)

class EvidencePureTests(unittest.TestCase):
    def test_frozen_contract_rows(self):
        data = fixture()
        self.assertEqual(len(data["cases"]), 31)
        self.assertTrue(all(c["status"] == "NOT_RUN" for c in data["cases"]))
        self.assertEqual(len(data["future_contracts"]), 9)

    def test_valid_synthetic_C_and_A_fields(self):
        self.assertEqual(validated()["evidence_state"], "SUFFICIENT")
        a = validated("A01")
        self.assertTrue(a["state_projection"]["app_container"])
        self.assertIn("ENV_INTEGRITY_BELOW_REQUIRED", a["reason_codes"])
        self.assertIn("ENV_APPCONTAINER_NOT_ALLOWED_FOR_ROLE", a["reason_codes"])

    def test_unknown_coverage_and_expiry_are_not_true(self):
        for cid in ("B01", "B02", "B03"):
            with self.subTest(case=cid):
                out = validated(cid)
                self.assertIsNone(out["state_projection"]["outer_job_clear"])
                self.assertIn("outer_job_clear", out["required_evidence"])

    def test_B07_both_missing_and_TTL_boundary(self):
        self.assertIsNone(validated("B07", 0)["state_projection"]["outer_job_clear"])
        self.assertIs(validated("B07", 1)["state_projection"]["outer_job_clear"], True)

    def test_bad_source_role_knowledge_time_and_conflicts(self):
        for cid, variants in (("A05",1),("A06",1),("B04",3),("B06",2),("B08",3),("B09",1)):
            for n in range(variants):
                with self.subTest(case=cid, variant=n):
                    with self.assertRaises(Rejected):
                        validated(cid,n)

    def test_hash_is_externally_bound_not_self_resealed(self):
        env = case_envelope()
        original = raw_sha(evidence_bytes(env))
        env["items"][0]["value"] = True
        with self.assertRaisesRegex(Rejected, "ENV_INPUT_HASH_MISMATCH"):
            validate_evidence(evidence_bytes(env), original, metadata(env))

    def test_strict_integrity_variants_and_duplicate_JSON(self):
        for n in range(3):
            with self.assertRaises(Rejected):
                validated("C06", n)
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.5}', b'\xef\xbb\xbf{}'):
            with self.assertRaises(Rejected):
                decode(raw)

    def test_missing_supporting_evidence_separate_from_policy(self):
        out = validated("B05")
        self.assertEqual(out["evidence_state"], "INSUFFICIENT")
        self.assertTrue(out["state_projection"]["outer_job_clear"])
        self.assertIn("supporting_attestation", out["required_evidence"])

    def test_request_scope_and_types(self):
        req = metadata(case_envelope())
        request(req)
        req["task_ref"]["task_kind"] = "TASK:FINANCE_REFUND"
        with self.assertRaises(Rejected):
            request(req)
