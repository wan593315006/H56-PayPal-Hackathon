"""Private storage fixture and native reassessment test source; NOT_RUN."""
import copy
import unittest
from unittest.mock import patch
from pathlib import Path
from offline_qualification_v1.contracts import (BOUNDARY, SEMANTIC_FIELDS, canonical,
    digest, raw_sha, seal, Rejected)
from offline_qualification_v1.records import RecordStore
from offline_qualification_v1.tests.test_evidence import metadata, case_envelope, evidence_bytes
TEST_ROOT = None

def fixture_root():
    # Explicit test-module input from a separately approved, pinned outer runner.
    # No additional environment variable or product-default scratch directory.
    value = TEST_ROOT
    if not value:
        raise RuntimeError("EXPLICIT_APPROVED_TEST_ROOT_REQUIRED")
    root = Path(value)
    if not root.is_absolute() or not root.is_dir():
        raise RuntimeError("EXPLICIT_APPROVED_TEST_ROOT_REQUIRED")
    return root

def store_fixture(req, claim):
    core = {k: None for k in SEMANTIC_FIELDS}
    core.update(schema="H56_OFFLINE_ASSESSMENT_RECORD_V1", assessment_id=claim["assessment_id"],
        parent_decision_ref=req["parent_decision_ref"], task_ref=req["task_ref"], environment_id=req["environment_id"],
        evidence_grade="SYNTHETIC_ONLY", raw_evidence_sha256=req["raw_evidence_sha256"],
        source_binding=dict(source_manifest_sha256=req["source_manifest_sha256"]),
        asset_binding=dict(manifest_sha256=req["asset_manifest_sha256"]),
        as_of=req["as_of"], admission_candidate="NO_DECISION", reason_codes=["PURE_STORAGE_FIXTURE"],
        required_evidence=[], boundary=dict(BOUNDARY), stage="INPUT",
        failure=dict(code="PURE_STORAGE_FIXTURE_NOT_NATIVE", exception_type="NotExecuted"))
    return seal(core)

class RecordsPureTests(unittest.TestCase):
    def test_R04_application_checks_changed_valid_material_before_core(self):
        from offline_qualification_v1.assessment import evaluate
        store = RecordStore(fixture_root(),"oq_app_conflict",create=True)
        env = case_envelope()
        req = metadata(env)
        claim,_ = store.reserve(req)
        store.commit(store_fixture(req,claim),claim)
        changes = []
        changed_env = copy.deepcopy(env)
        changed_env["items"][0]["value"] = True
        changed = copy.deepcopy(req)
        changed["raw_evidence_sha256"] = raw_sha(evidence_bytes(changed_env))
        changes.append((changed_env,changed))
        for field,value in (("as_of","2026-10-24T00:05:01Z"),("interface_version","1.0.1")):
            changed = copy.deepcopy(req)
            changed[field] = value
            changes.append((env,changed))
        for data, changed in changes:
            with patch("offline_qualification_v1.assessment.source_manifest") as source, \
                 patch("offline_qualification_v1.core_bridge.compute") as native:
                with self.assertRaisesRegex(Rejected,"IDEMPOTENCY_CONFLICT"):
                    evaluate(evidence_bytes(data),changed,store)
                self.assertEqual(source.call_count,0)
                self.assertEqual(native.call_count,0)

    def test_parent_committed_binding_hash_task_env_and_depth_guards(self):
        from offline_qualification_v1.assessment import check_parent
        store = RecordStore(fixture_root(),"oq_parent_bindings",create=True)
        req = metadata(case_envelope())
        claim,_ = store.reserve(req)
        parent = store.commit(store_fixture(req,claim),claim)
        child = copy.deepcopy(req)
        child.update(request_id="child_fixture",parent_decision_ref=parent["reference"])
        self.assertIsNotNone(check_parent(child,store))
        for field in ("artifact_sha256","semantic_sha256","journal_event_sha256"):
            bad = copy.deepcopy(child)
            bad["parent_decision_ref"][field] = "1"*64
            with self.assertRaises(Rejected):
                check_parent(bad,store)
        for field in ("environment_id","task_ref","source_manifest_sha256","asset_manifest_sha256"):
            bad = copy.deepcopy(child)
            bad[field] = dict(child["task_ref"],task_id="other_task") if field == "task_ref" else \
                         "other_env" if field == "environment_id" else "1"*64
            with self.assertRaises(Rejected):
                check_parent(bad,store)
        cclaim,_ = store.reserve(child)
        committed_child = store.commit(store_fixture(child,cclaim),cclaim)
        grandchild = copy.deepcopy(child)
        grandchild.update(request_id="grandchild_fixture",parent_decision_ref=committed_child["reference"])
        with self.assertRaises(Rejected):
            check_parent(grandchild,store)

    def test_R03_concurrent_reservation_has_only_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        root = fixture_root()
        stores = [RecordStore(root, "oq_concurrent", create=True) for _ in range(2)]
        req = metadata(case_envelope())
        barrier = Barrier(2)
        def reserve(index):
            barrier.wait(timeout=5)
            try:
                stores[index].reserve(req)
                return "WINNER"
            except Rejected as exc:
                return exc.code.partition(":")[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, (0,1)))
        self.assertEqual(results.count("WINNER"),1)
        self.assertEqual(results.count("REQUEST_IN_PROGRESS_OR_RECOVERY_REQUIRED"),1)

    def test_R03_pending_committed_and_C04_read(self):
        store = RecordStore(fixture_root(), "oq_pure_pending", create=True)
        req = metadata(case_envelope())
        claim, previous = store.reserve(req)
        self.assertIsNone(previous)
        with self.assertRaisesRegex(Rejected, "REQUEST_IN_PROGRESS"):
            store.reserve(req)
        result = store.commit(store_fixture(req,claim), claim)
        before = (store.root / "artifacts" / (claim["assessment_id"][7:] + ".json")).read_bytes()
        _, again = store.reserve(req)
        self.assertEqual(result["reference"], again["reference"])
        self.assertFalse(again["native_recomputed"])
        self.assertEqual(before, (store.root / "artifacts" / (claim["assessment_id"][7:] + ".json")).read_bytes())

    def test_R04_same_key_different_material(self):
        store = RecordStore(fixture_root(), "oq_pure_conflict", create=True)
        req = metadata(case_envelope())
        store.reserve(req)
        for field in ("raw_evidence_sha256", "as_of", "interface_version"):
            changed = copy.deepcopy(req)
            changed[field] = "1"*64 if field.endswith("sha256") else "different"
            with self.assertRaisesRegex(Rejected, "IDEMPOTENCY_CONFLICT"):
                store.reserve(changed)

    def test_explicit_independent_root_and_session(self):
        with self.assertRaises(Rejected):
            RecordStore(None, "oq_missing")
        with self.assertRaises(Rejected):
            RecordStore(fixture_root(), "old_TaskService_session")

    def test_wrong_parent_never_reopens_TaskService(self):
        from offline_qualification_v1.assessment import check_parent
        store = RecordStore(fixture_root(), "oq_parent_guard", create=True)
        req = metadata(case_envelope())
        req["parent_decision_ref"] = dict(assessment_id="ASSESS:"+"0"*64,
            decision_id="DECISION:"+"0"*64, semantic_sha256="0"*64,
            artifact_sha256="0"*64, journal_event_sha256="0"*64)
        with self.assertRaises(Rejected):
            check_parent(req,store)

class RecordsNativeTests(unittest.TestCase):
    def test_R01_R02_explicit_new_assessments_preserve_parent(self):
        from offline_qualification_v1.assessment import evaluate
        from offline_qualification_v1.tests.test_core_chain import bindings
        for case_id, expected in (("B01","DEFER"),("A01","INFEASIBLE")):
            store = RecordStore(fixture_root(), "oq_native_parent_"+case_id, create=True)
            env = case_envelope(case_id)
            _, req = bindings(env, "parent_"+case_id)
            first = evaluate(evidence_bytes(env), req, store)
            path = store.root / "artifacts" / (first["record"]["assessment_id"][7:]+".json")
            before = path.read_bytes()
            new_env = case_envelope("C01")
            _, child = bindings(new_env, "child_"+case_id)
            child["parent_decision_ref"] = first["reference"]
            second = evaluate(evidence_bytes(new_env), child, store)
            self.assertEqual(first["record"]["c2_projection"]["decision"],expected)
            self.assertEqual(second["record"]["c2_projection"]["decision"],"FEASIBLE")
            self.assertNotEqual(first["record"]["history"]["history_id"],second["record"]["history"]["history_id"])
            self.assertEqual(path.read_bytes(), before)
            grandchild = copy.deepcopy(child)
            grandchild.update(request_id="grandchild_"+case_id,parent_decision_ref=second["reference"])
            with self.assertRaisesRegex(Rejected,"ENV_PARENT_BINDING_MISMATCH"):
                evaluate(evidence_bytes(new_env), grandchild, store)
