"""Native-only test source. Collect/run only under separate A-R-CORE grant."""
import unittest
from pathlib import Path
from offline_qualification_v1.contracts import raw_sha
from offline_qualification_v1.tests.test_evidence import (case_envelope, evidence_bytes,
    metadata, validated)

def bindings(env, request_id="native_request"):
    product = Path(__file__).absolute().parents[2]
    root = product / "offline_qualification_v1"
    req = metadata(env, request_id)
    req["source_manifest_sha256"] = raw_sha((root / "SOURCE_MANIFEST.json").read_bytes())
    req["asset_manifest_sha256"] = raw_sha((root / "assets" / "manifest.json").read_bytes())
    return product, req

class NativeCoreTests(unittest.TestCase):
    def test_three_native_cases_and_all_nullable_variants(self):
        from offline_qualification_v1.assets import load_assets, source_manifest
        from offline_qualification_v1.core_bridge import compute
        from offline_qualification_v1.evidence import validate_evidence
        from offline_qualification_v1.tests.test_boundary import forbidden_call_sentinels
        # These direct pure-native unit cases have separate named operation grants;
        # application request deduplication is tested through assessment.evaluate.
        cases = [("A01",0,"INFEASIBLE"),("A02",0,"INFEASIBLE"),("A03",0,"INFEASIBLE"),
                 ("A04",0,"INFEASIBLE"),("B01",0,"DEFER"),("B02",0,"DEFER"),
                 ("B03",0,"DEFER"),("B05",0,"NEED_MORE_EVIDENCE"),
                 ("B07",0,"DEFER"),("B07",1,"FEASIBLE"),("B10",0,"INFEASIBLE"),
                 ("C01",0,"FEASIBLE")]
        for cid, n, expected in cases:
            with self.subTest(case=cid, variant=n):
                env = case_envelope(cid,n)
                product, req = bindings(env)
                source_manifest(req["source_manifest_sha256"])
                assets = load_assets(req["asset_manifest_sha256"])
                with forbidden_call_sentinels() as forbidden_calls:
                    out = compute(validate_evidence(evidence_bytes(env), req["raw_evidence_sha256"], req),
                                  assets, req, product)
                    self.assertEqual(forbidden_calls,[])
                self.assertEqual(out["c2_projection"]["decision"], expected)
                self.assertFalse(out["c2_projection"]["authority_granted"])
                self.assertFalse(out["c2_projection"]["execution_permitted"])
                calls = [c["call"] for c in out["mapping_trace"]["native_calls"]]
                for label in ("K0.Fact.create","K1.StateCompiler.compile","C1.Catalog.from_mapping",
                              "C1.Catalog.verify_identity","C1.Catalog.require_definition",
                              "C2.Evaluator.project","C2.Projection.verify"):
                    self.assertIn(label, calls)
                self.assertEqual(out["c1_catalog"]["catalog_hash"], out["c2_reference"]["catalog_hash"])
                if cid == "A04":
                    self.assertIn("ENV_APPCONTAINER_NOT_ALLOWED_FOR_ROLE",out["reason_codes"])
                    self.assertIn("outer_job_clear",validated(cid)["required_evidence"])
                if cid == "B05":
                    self.assertIn("EVIDENCE_REQUIREMENT_NOT_SATISFIED",out["reason_codes"])

    def test_X04_original_K1_active_conflict_not_latest_wins(self):
        from offline_qualification_v1.assets import load_assets
        from offline_qualification_v1.core_bridge import load_core, compile_snapshot, Trace, private_diagnostic
        product, req = bindings(case_envelope())
        native, _ = load_core(product, req["source_manifest_sha256"])
        p = native["Provenance"]("SYNTHETIC_FIXTURE_V1","synthetic_env","1.0.0",
                                  "SYNTHETIC_ENV:synthetic_env","1.0.0",("fixture",))
        history = native["History"].empty()
        for n, value in enumerate((True,False)):
            fact = native["Fact"].create(fact_type="assertion", subject_id="ENV:synthetic_env",
                occurred_at="2026-10-24T00:04:00Z",
                payload=dict(state_projection=dict(outer_job_clear=value), fixture_ordinal=n), provenance=p)
            history = history.append(fact)
        versions = native["VersionTuple"](**load_assets(req["asset_manifest_sha256"])["policy"]["version_tuple"])
        trace = Trace(product)
        snapshot, projection = None, None
        with self.assertRaises(native["StateCompilationError"]) as caught:
            snapshot = compile_snapshot(history,versions,native,trace)
        self.assertIsNone(snapshot)
        self.assertIsNone(projection)
        self.assertEqual(trace.events[-1]["call"],"K1.StateCompiler.compile")
        self.assertEqual(trace.events[-1]["status"],"FAILED")
        self.assertIn("conflicting active projections",private_diagnostic(caught.exception)["message"])
