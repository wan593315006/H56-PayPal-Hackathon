"""Safe boundary fixture source only; never runs a dangerous probe."""
import copy
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import contextmanager
from types import ModuleType
from offline_qualification_v1.contracts import (Rejected, BOUNDARY, semantic_guard,
    validate_boundary, decode, canonical, raw_sha, disjoint_roots)
from offline_qualification_v1.assets import load_assets
from offline_qualification_v1.tests.test_evidence import fixture
from runtime_windows.source_identity import _safe_name, _check_stat

@contextmanager
def forbidden_call_sentinels():
    """Fake modules only; never imports or probes a real dangerous consumer."""
    calls, modules = [], {}
    targets = {
        "ctypes": ("WinDLL","CDLL"),
        "subprocess": ("run","Popen","call"),
        "socket": ("socket","create_connection"),
        "requests": ("get","post","request"),
        "runtime_windows.candidate_host": ("CandidateHost",),
        "runtime_windows.tasks": ("TaskService",),
        "runtime_windows.assembly.loader": ("load_core",),
        "runtime_windows.assembly.pipeline": ("compute",),
        "runtime_windows.host_contract": ("_issue_permit",),
    }
    for name, entries in targets.items():
        module = ModuleType(name)
        for entry in entries:
            def stop(*args, _label=name+"."+entry, **kwargs):
                calls.append(_label)
                raise AssertionError("FORBIDDEN_CALL_SENTINEL:" + _label)
            setattr(module,entry,stop)
        modules[name] = module
    with patch.dict("sys.modules", modules):
        yield calls

class BoundaryPureTests(unittest.TestCase):
    def test_native_failure_and_commit_failure_preserve_both_diagnostics(self):
        from offline_qualification_v1.assessment import evaluate, DiagnosticCommitFailure
        from offline_qualification_v1.core_bridge import NativeFailure, private_diagnostic
        from offline_qualification_v1.tests.test_evidence import metadata, case_envelope, evidence_bytes
        from offline_qualification_v1.contracts import digest
        env = case_envelope()
        req = metadata(env)
        native_error = private_diagnostic(ValueError("SYNTHETIC_NATIVE_FAILURE"))
        store = SimpleNamespace(check_conflict=lambda value:None,
            reserve=lambda value: (dict(assessment_id="ASSESS:"+digest(value)),None))
        store.commit = Mock(side_effect=OSError("SYNTHETIC_COMMIT_FAILURE"))
        with patch("offline_qualification_v1.assessment.source_manifest", return_value=(Path("/"),{})), \
             patch("offline_qualification_v1.assessment.load_assets", return_value=dict(hashes={})), \
             patch("offline_qualification_v1.assessment.validate_evidence",
                   return_value=dict(reason_codes=[],required_evidence=[])), \
             patch("offline_qualification_v1.core_bridge.compute",
                   side_effect=NativeFailure("K1",{},"ValueError","fixture",native_error)):
            with self.assertRaises(DiagnosticCommitFailure) as caught:
                evaluate(evidence_bytes(env),req,store)
        self.assertEqual(caught.exception.native_diagnostic,native_error)
        self.assertIsInstance(caught.exception.__cause__,OSError)
        self.assertIn("SYNTHETIC_COMMIT_FAILURE",str(caught.exception.__cause__))
        private = private_diagnostic(caught.exception)
        self.assertIn("SYNTHETIC_COMMIT_FAILURE",private["traceback"])

    def test_private_diagnostic_handoff_is_not_semantic(self):
        import io
        from contextlib import redirect_stderr
        from offline_qualification_v1.core_bridge import private_diagnostic
        from offline_qualification_v1.cli import emit_private_diagnostic
        diagnostic = private_diagnostic(ValueError("SYNTHETIC_DIAGNOSTIC_ONLY"))
        output = io.StringIO()
        with redirect_stderr(output):
            emit_private_diagnostic(diagnostic)
        self.assertIn("SYNTHETIC_DIAGNOSTIC_ONLY",output.getvalue())
        with self.assertRaises(Rejected):
            semantic_guard(dict(failure=dict(raw_error=diagnostic)))

    def test_root_contract_rejects_equal_and_both_ancestries(self):
        root = Path(__file__).absolute().anchor
        source = Path(root) / "synthetic_source"
        output = Path(root) / "synthetic_output"
        self.assertTrue(disjoint_roots(source,output))
        for a,b in ((source,source),(source,source/"nested"),(source/"nested",source)):
            self.assertFalse(disjoint_roots(a,b))

    def test_X03_missing_pyc_and_self_cycle_stop_before_native_import(self):
        import json
        from offline_qualification_v1.assets import source_manifest
        from offline_qualification_v1.core_bridge import load_core, VerifiedNativeFinder
        product = Path(__file__).absolute().parents[2]
        path = product/"offline_qualification_v1"/"SOURCE_MANIFEST.json"
        raw = path.read_bytes()
        original = json.loads(raw)
        from offline_qualification_v1 import assets
        real_read = assets.read_bytes
        native_member = next(m for m in original["runtime_required"] if
                             "/src/k0_fact_foundation/contracts.py" in m["path"])
        def missing(target, maximum=1048576, size=None):
            if Path(target) == product/native_member["path"]:
                raise FileNotFoundError("SYNTHETIC_MISSING_SOURCE")
            return real_read(target, maximum, size)
        with patch("offline_qualification_v1.assets.read_bytes", side_effect=missing), \
             patch("offline_qualification_v1.core_bridge.importlib.import_module") as imports:
            with self.assertRaises((Rejected,OSError)):
                load_core(product,raw_sha(raw))
            self.assertEqual(imports.call_count,0)
        for bad_name in ("offline_qualification_v1/SOURCE_MANIFEST.json",
                         native_member["path"][:-3]+".pyc"):
            bad = copy.deepcopy(original)
            next(m for m in bad["runtime_required"] if m["path"] == native_member["path"])["path"] = bad_name
            changed = canonical(bad).encode("utf-8")
            def mutated(target, maximum=1048576, size=None):
                return changed if Path(target) == path else real_read(target,maximum,size)
            with patch("offline_qualification_v1.assets.read_bytes", side_effect=mutated):
                with self.assertRaisesRegex(Rejected,"SOURCE_MEMBER_SCOPE_MISMATCH"):
                    source_manifest(raw_sha(changed))
        finder = VerifiedNativeFinder(product,original)
        with self.assertRaisesRegex(Rejected,"UNREGISTERED_NATIVE_MODULE"):
            finder.find_spec("k0_fact_foundation.unregistered_or_pyc")

    def test_X05_invalid_input_has_zero_forbidden_and_native_calls(self):
        from offline_qualification_v1.assessment import evaluate
        from offline_qualification_v1.tests.test_evidence import metadata, case_envelope, evidence_bytes
        env = case_envelope()
        env["evidence_grade"] = "CURRENT_HOST"
        req = metadata(env)
        store = SimpleNamespace(check_conflict=lambda req:None)
        with forbidden_call_sentinels() as calls, \
             patch("offline_qualification_v1.assessment.source_manifest", return_value=(Path("/"),{})), \
             patch("offline_qualification_v1.assessment.load_assets", return_value={}), \
             patch("offline_qualification_v1.core_bridge.compute") as native:
            with self.assertRaises(Rejected):
                evaluate(evidence_bytes(env),req,store)
            self.assertEqual(native.call_count,0)
            self.assertEqual(calls,[])

    def test_X01_hostile_path_strings_rejected_without_read(self):
        for value in ("../other", "C:/private", "//other/private", "a/../b", "x\\\\y"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _safe_name(value)

    def test_X02_reparse_is_metadata_fixture_not_real_link(self):
        for mode, attrs in ((stat.S_IFLNK,0),(stat.S_IFREG,0x400)):
            with self.assertRaises(ValueError):
                _check_stat(SimpleNamespace(st_mode=mode,st_file_attributes=attrs,st_nlink=1),
                            False,"pure_fixture")

    def test_A08_recursive_authority_and_runtime_grade_guards(self):
        validate_boundary(dict(BOUNDARY))
        for value in (dict(evidence_grade="CURRENT_HOST"),
                      dict(source_binding=dict(authority_granted=True)),
                      dict(mapping_trace=dict(pid=123)),
                      dict(failure=dict(error_text="C:/private/path"))):
            with self.assertRaises(Rejected):
                semantic_guard(value)

    def test_C05_B09_C06_asset_resealing_cannot_change_fixed_contract(self):
        root = Path(__file__).absolute().parents[1] / "assets"
        import json
        manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
        bodies = {e["path"]: (root/e["path"]).read_bytes() for e in manifest["members"]}
        variants = [("capability_catalog.json","capability_id","CAP:FINANCE_REFUND"),
                    ("state_mapping.json","state_pattern","DEVSECOPS"),
                    ("capability_catalog.json","contract_commit","1"*40),
                    ("capability_catalog.json","catalog_version","9.0.0"),
                    ("environment_policy.json","authority_state","DECLARED_UNKNOWN")]
        variants += [("environment_policy.json","budget",v) for v in (True,"1",1.5)]
        for name, field, value in variants:
            with self.subTest(name=name, field=field, value=value):
                changed = json.loads(bodies[name].decode("utf-8"))
                if field == "capability_id":
                    changed["definition_body"][field] = value
                elif field == "authority_state":
                    changed["synthetic_assumption"][field] = value
                elif field == "budget":
                    changed["budget_declaration"]["available_units"] = value
                else:
                    changed[field] = value
                raw = canonical(changed).encode("utf-8")
                current = copy.deepcopy(manifest)
                next(e for e in current["members"] if e["path"] == name).update(size=len(raw),sha256=raw_sha(raw))
                manifest_raw = canonical(current).encode("utf-8")
                def fake_read(path, maximum=1048576, size=None):
                    leaf = Path(path).name
                    return manifest_raw if leaf == "manifest.json" else raw if leaf == name else bodies[leaf]
                with patch("offline_qualification_v1.assets.read_bytes", side_effect=fake_read):
                    with self.assertRaises((Rejected,ValueError)):
                        load_assets(raw_sha(manifest_raw))

    def test_X03_fake_preload_is_not_native_source(self):
        # No original core import: a fake sys.modules entry must stop first.
        import sys
        from offline_qualification_v1.core_bridge import load_core
        from offline_qualification_v1.contracts import raw_sha
        product = Path(__file__).absolute().parents[2]
        pin = raw_sha((product/"offline_qualification_v1"/"SOURCE_MANIFEST.json").read_bytes())
        fake = SimpleNamespace(__file__="not-a-native-source.py")
        with patch.dict(sys.modules, {"k0_fact_foundation":fake}):
            with self.assertRaises(Rejected):
                load_core(product,pin)

    def test_X05_no_forbidden_imports_or_calls_in_new_product_text(self):
        # Text check is narrow evidence, never an OS isolation assertion.
        root = Path(__file__).absolute().parents[1]
        forbidden = ("import ctypes", "import subprocess", "import socket", "import requests",
                     "TaskService(", ".dispatch(", "CandidateHost(", "pipeline.compute(",
                     "admit_runtime(", "_issue_permit(")
        for name in ("__init__.py","contracts.py","assets.py","evidence.py",
                     "core_bridge.py","assessment.py","records.py","cli.py"):
            text = (root/name).read_text(encoding="utf-8")
            self.assertTrue(all(word not in text for word in forbidden),name)
