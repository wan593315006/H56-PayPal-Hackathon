"""Approved pure-native bridge source. Import performs no native loading."""
import importlib
import importlib.util
import sys
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path

from runtime_windows.source_identity import parse_public_lock, verify_public_lock
from runtime_windows.adapters.bounded_rules import evaluate
from .assets import read_bytes, source_manifest
from .contracts import (ALIASES, Rejected, canonical, digest, need, raw_sha)

PROJECTS = {
    "k0_fact_foundation": "k0_canonical_fact_foundation_v1",
    "k1_state_derivation": "k1_state_derivation_foundation_v1",
    "candidate_canonical_capability_contract": "candidate_canonical_capability_contract_v0_1",
    "candidate_capability_feasibility_projection": "candidate_capability_feasibility_projection_v0_1",
}
TRUSTED = {}
EXPORTS = {}
LOCK_SHA = "060bbaa1976d243b9441a295c889fdf5dfa2252db66381ae669e6f5804ff07e3"

class VerifiedSourceLoader:
    """Future authorized import of only preverified immutable source bytes."""
    def __init__(self, origin, raw):
        self.origin, self.raw = origin, raw
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        module.__file__ = str(self.origin)
        module.__cached__ = None
        # This is not an evidence/plugin evaluator. Only hash-pinned original
        # native source selected by VerifiedNativeFinder can reach this branch.
        code = compile(self.raw, str(self.origin), "exec", dont_inherit=True, optimize=0)
        exec(code, module.__dict__)

class VerifiedNativeFinder:
    def __init__(self, product, manifest):
        self.product, self.index = product, {}
        for package, project in PROJECTS.items():
            prefix = ("runtime_binding_v1_20261024/engineering/vendor/clean_core_projects/"
                      + project + "/src/")
            for member in manifest["runtime_required"]:
                path = member["path"]
                if not path.startswith(prefix + package + "/") or not path.endswith(".py"):
                    continue
                tail = path[len(prefix):]
                package_file = tail.endswith("/__init__.py")
                name = (tail[:-12] if package_file else tail[:-3]).replace("/", ".")
                need(name not in self.index, "DUPLICATE_NATIVE_MODULE", "SOURCE")
                self.index[name] = (member, package_file)
    def find_spec(self, fullname, path=None, target=None):
        if not any(fullname == p or fullname.startswith(p + ".") for p in PROJECTS):
            return None
        # Raising, rather than returning None, prevents any next finder/path,
        # installed package, zip, cached bytecode or plugin fallback.
        need(fullname in self.index, "UNREGISTERED_NATIVE_MODULE", "SOURCE")
        member, package_file = self.index[fullname]
        origin = self.product.joinpath(*member["path"].split("/"))
        raw = read_bytes(origin, size=member["size"])
        need(raw_sha(raw) == member["sha256"], "NATIVE_SOURCE_CHANGED_BEFORE_IMPORT", "SOURCE")
        return importlib.util.spec_from_file_location(fullname, str(origin),
            loader=VerifiedSourceLoader(origin, raw),
            submodule_search_locations=[str(origin.parent)] if package_file else None)

def private_diagnostic(exc):
    """Bounded raw diagnostic handoff, explicitly outside semantic records."""
    formatted = "".join(traceback.TracebackException.from_exception(
        exc, limit=12, capture_locals=False).format(chain=True))
    message = str(exc)
    return dict(scope="PRIVATE_RAW_EXCEPTION_NOT_SEMANTIC", exception_type=type(exc).__name__,
                message=message[:2048], traceback=formatted[:12288],
                truncated=len(message) > 2048 or len(formatted) > 12288)

def plain(value):
    if is_dataclass(value):
        value = asdict(value)
    if type(value) is dict:
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if value is None or type(value) in (str, int, bool):
        return value
    return {"native_object_type": type(value).__module__ + "." + type(value).__name__}

def load_core(product, expected_source_sha):
    """Called only after exclusive request claim, never during source review."""
    checked_product, manifest = source_manifest(expected_source_sha)
    need(checked_product == product, "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    raw = read_bytes(product / "runtime_windows" / "public-source-lock.json")
    need(raw_sha(raw) == LOCK_SHA, "ENV_SOURCE_OR_VERSION_MISMATCH", "SOURCE")
    provenance = verify_public_lock(product / "runtime_binding_v1_20261024", parse_public_lock(raw))
    members = {m["path"] for m in manifest["runtime_required"]}
    def relevant(name):
        return any(name == p or name.startswith(p + ".") for p in PROJECTS)
    for name, module in list(sys.modules.items()):
        if relevant(name):
            need(name in TRUSTED and TRUSTED[name] is module,
                 "UNTRUSTED_PRELOADED_NATIVE_MODULE", "SOURCE")
    roots = []
    for project in PROJECTS.values():
        root = product / "runtime_binding_v1_20261024" / "engineering" / "vendor" / "clean_core_projects" / project / "src"
        need(str(root) not in roots, "DUPLICATE_NATIVE_ROOT", "SOURCE")
        roots.append(str(root))
    # Fixed source finder takes ownership of all four native prefixes BEFORE
    # execution. The standard loader is never allowed to read a native pyc.
    finder = VerifiedNativeFinder(product, manifest)
    sys.meta_path.insert(0, finder)
    try:
        mods = {
            "k0": importlib.import_module("k0_fact_foundation.contracts"),
            "history": importlib.import_module("k0_fact_foundation.history"),
            "k1": importlib.import_module("k1_state_derivation.state_compiler"),
            "c1": importlib.import_module("candidate_canonical_capability_contract.contracts"),
            "catalog": importlib.import_module("candidate_canonical_capability_contract.catalog"),
            "c2": importlib.import_module("candidate_capability_feasibility_projection.contracts"),
            "evaluator": importlib.import_module("candidate_capability_feasibility_projection.evaluator"),
        }
        for name, module in list(sys.modules.items()):
            if not relevant(name):
                continue
            origin = getattr(module, "__file__", None)
            need(type(origin) is str and origin.endswith(".py"), "NATIVE_ORIGIN_NOT_SOURCE", "SOURCE")
            path = Path(origin).absolute()
            try:
                relative = path.relative_to(product).as_posix()
            except ValueError:
                raise Rejected("NATIVE_ORIGIN_OUTSIDE_SOURCE", "SOURCE") from None
            expected_prefix = name.split(".")[0]
            expected_root = product / "runtime_binding_v1_20261024" / "engineering" / "vendor" / "clean_core_projects" / PROJECTS[expected_prefix] / "src"
            need(path.is_relative_to(expected_root) if hasattr(path, "is_relative_to")
                 else str(path).startswith(str(expected_root) + "/") or str(path).startswith(str(expected_root) + "\\"),
                 "NATIVE_ORIGIN_MISMATCH", "SOURCE")
            need(relative in members, "UNREGISTERED_NATIVE_MODULE", "SOURCE")
            if name in TRUSTED:
                need(TRUSTED[name] is module, "NATIVE_MODULE_REPLACED", "SOURCE")
            TRUSTED[name] = module
        selected = {
            "Fact": mods["k0"].Fact, "Provenance": mods["k0"].FactProvenance,
            "VersionTuple": mods["k0"].VersionTuple, "History": mods["history"].FactHistory,
            "Compiler": mods["k1"].StateCompiler, "StateCompilationError": mods["k1"].StateCompilationError,
            "Definition": mods["c1"].CapabilityDefinition, "Catalog": mods["catalog"].CanonicalCapabilityCatalog,
            "Reference": mods["c2"].CapabilityCatalogReference,
            "Assertion": mods["c2"].CapabilityAvailabilityAssertion,
            "Context": mods["c2"].FeasibilityContext, "native_hash": mods["c2"].canonical_sha256,
            "Evaluator": mods["evaluator"].CandidateCapabilityFeasibilityEvaluator,
        }
        if EXPORTS:
            need(set(EXPORTS) == set(selected) and
                 all(EXPORTS[k] is v for k, v in selected.items()), "NATIVE_EXPORT_REPLACED", "SOURCE")
        EXPORTS.update(selected)
        return selected, provenance
    finally:
        sys.meta_path[:] = [item for item in sys.meta_path if item is not finder]

class NativeFailure(Rejected):
    def __init__(self, stage, outputs, exception_type, cause_code, diagnostic):
        super().__init__("ENV_CORE_FAILURE", stage)
        self.outputs, self.exception_type = outputs, exception_type
        self.cause_code = cause_code
        self.raw_diagnostic = diagnostic

class Trace:
    def __init__(self, product):
        self.product, self.events = product, []
    def call(self, label, fn, *args, **kwargs):
        module = sys.modules[fn.__module__]
        relative = Path(module.__file__).absolute().relative_to(self.product).as_posix()
        event = dict(ordinal=len(self.events) + 1, call=label, source=relative,
                     input_sha256=digest(plain(dict(args=args, kwargs=kwargs))), status="STARTED")
        self.events.append(event)
        try:
            output = fn(*args, **kwargs)
        except Exception as exc:
            event.update(status="FAILED", exception_type=type(exc).__name__)
            raise
        event.update(status="RETURNED", output_sha256=digest(plain(output)))
        return output

def compile_snapshot(history, version_tuple, native, trace):
    """Shared I03 path; returns only an original verified K1 Snapshot."""
    compiler = trace.call("K1.StateCompiler", native["Compiler"])
    snapshot = trace.call("K1.StateCompiler.compile", compiler.compile, history, version_tuple)
    trace.call("K1.Snapshot.verify", snapshot.verify)
    return snapshot

def compute(validated, assets, req, product):
    """Only synthetic candidate computation; no formal writer or dispatcher."""
    output = {k: None for k in ("fact_cores", "history", "snapshot", "version_tuple",
        "mapping_trace", "c1_catalog", "c1_definition", "c2_reference",
        "availability_assertion", "c2_context", "c2_projection")}
    trace, stage = Trace(product), "SOURCE"
    try:
        native, provenance = load_core(product, req["source_manifest_sha256"])
        output["source_validation"] = dict(identity_receipt=provenance,
            identity_receipt_scope="BYTE_CHECK_BEFORE_NATIVE_IMPORT", recorded_native_calls=0)
        stage = "K0"
        source = trace.call("K0.FactProvenance", native["Provenance"],
            source_id="SYNTHETIC_FIXTURE_V1", object_id=req["environment_id"],
            object_version=req["raw_evidence_sha256"],
            environment_fingerprint="SYNTHETIC_ENV:" + req["environment_id"] + ":" + provenance["vendor_fingerprint"],
            schema_version="1.0.0", evidence_refs=(req["raw_evidence_sha256"],
                req["asset_manifest_sha256"], digest(req["task_ref"])))
        fact = trace.call("K0.Fact.create", native["Fact"].create, fact_type="assertion",
            subject_id="ENV:" + req["environment_id"], occurred_at=validated["occurred_at"],
            payload=dict(state_projection=validated["state_projection"],
                         normalization=validated["normalized_evidence"],
                         occurred_at_derivation=validated["occurred_at_derivation"]),
            provenance=source)
        output["fact_cores"] = [dict(fact_id=fact.fact_id, **fact.canonical_core())]
        history = trace.call("K0.FactHistory.empty", native["History"].empty)
        history = trace.call("K0.FactHistory.append", history.append, fact)
        trace.call("K0.FactHistory.verify", history.verify)
        output["history"] = dict(history_id=history.history_id, fact_ids=[f.fact_id for f in history.facts])
        versions = trace.call("K0.VersionTuple", native["VersionTuple"],
                              **assets["policy"]["version_tuple"])
        output["version_tuple"] = versions.to_dict()
        stage = "K1"
        snapshot = compile_snapshot(history, versions, native, trace)
        state = trace.call("K1.Snapshot.state_by_subject", snapshot.state_by_subject)
        output["snapshot"] = dict(snapshot_id=snapshot.snapshot_id,
            history_id=snapshot.history_id, version_tuple=versions.to_dict(),
            state=state, contributing_fact_ids=list(snapshot.contributing_fact_ids),
            provenance=snapshot.provenance())
        stage = "C1"
        cap = assets["capability"]
        definition_body = cap["definition_body"]
        definition_hash = trace.call("C1.Definition.expected_hash", native["Definition"].expected_hash, definition_body)
        definition = trace.call("C1.Definition.from_mapping", native["Definition"].from_mapping,
                                dict(definition_body, definition_hash=definition_hash))
        catalog_hash = trace.call("C1.Catalog.expected_hash", native["Catalog"].expected_hash,
            catalog_id=cap["catalog_id"], catalog_version=cap["catalog_version"],
            definitions=(definition,))
        catalog = trace.call("C1.Catalog.from_mapping", native["Catalog"].from_mapping,
            dict(catalog_id=cap["catalog_id"], catalog_version=cap["catalog_version"],
                 definitions=[definition.to_mapping()], catalog_hash=catalog_hash))
        trace.call("C1.Catalog.verify_identity", catalog.verify_identity)
        actual = trace.call("C1.Catalog.require_definition", catalog.require_definition,
                            definition.capability_id)
        output["c1_catalog"], output["c1_definition"] = catalog.to_mapping(), actual.to_mapping()
        stage = "MAPPING"
        rule = assets["mapping"]["policy_expression"]
        result = evaluate(rule, state["ENV:" + req["environment_id"]])
        mapping = dict(policy_result=result, policy_state=assets["mapping"]["policy_to_C2"][
            "null" if result is None else "true" if result is True else "false"],
            state_pattern=assets["mapping"]["state_pattern"], expression=rule,
            normalized_evidence=validated["normalized_evidence"], native_calls=trace.events)
        policy_preimage = dict(policy_asset_sha256=assets["hashes"]["environment_policy.json"],
            mapping_asset_sha256=assets["hashes"]["state_mapping.json"],
            mapping_trace={k:v for k,v in mapping.items() if k != "native_calls"},
            snapshot_id=snapshot.snapshot_id, as_of=req["as_of"])
        evidence_preimage = dict(raw_evidence_sha256=req["raw_evidence_sha256"],
            normalized_evidence=validated["normalized_evidence"],
            requirements=assets["policy"]["required_fields"], as_of=req["as_of"])
        budget_preimage = dict(budget_declaration=assets["policy"]["budget_declaration"],
                               snapshot_id=snapshot.snapshot_id)
        mapping["context_preimages"] = dict(policy=policy_preimage, evidence=evidence_preimage,
            budget=budget_preimage, authority=assets["policy"]["synthetic_assumption"],
            task=req["task_ref"], method=assets["policy"]["method_declaration"])
        output["mapping_trace"] = mapping
        stage = "C2"
        ref_body = dict(catalog_id=catalog.catalog_id, catalog_version=catalog.catalog_version,
            catalog_hash=catalog.catalog_hash, contract_project_id=cap["contract_project_id"],
            contract_commit=cap["contract_commit"], contract_manifest_sha256=cap["contract_manifest_sha256"],
            capability_id=actual.capability_id, definition_hash=actual.definition_hash)
        ref = trace.call("C2.Reference.from_mapping", native["Reference"].from_mapping,
            dict(ref_body, reference_hash=native["native_hash"](ref_body)))
        assertion_body = dict(cap["availability_body"], capability_id=actual.capability_id,
                              definition_hash=actual.definition_hash)
        assertion = trace.call("C2.Assertion.from_mapping", native["Assertion"].from_mapping,
            dict(assertion_body, assertion_hash=native["native_hash"](assertion_body)))
        context_body = dict(task_kind=req["task_ref"]["task_kind"], task_snapshot_hash=digest(req["task_ref"]),
            state_pattern=assets["mapping"]["state_pattern"],
            state_snapshot_hash=snapshot.snapshot_id.split(":",1)[1],
            method_id=assets["policy"]["method_declaration"]["method_id"],
            method_hash=digest(assets["policy"]["method_declaration"]),
            policy_state=mapping["policy_state"], policy_snapshot_hash=digest(policy_preimage),
            authority_state=assets["policy"]["synthetic_assumption"]["authority_state"],
            authority_snapshot_hash=digest(assets["policy"]["synthetic_assumption"]),
            budget_available_units=assets["policy"]["budget_declaration"]["available_units"],
            budget_snapshot_hash=digest(budget_preimage), evidence_state=validated["evidence_state"],
            evidence_snapshot_hash=digest(evidence_preimage))
        context = trace.call("C2.Context.from_mapping", native["Context"].from_mapping,
            dict(context_body, context_hash=native["native_hash"](context_body)))
        output["c2_reference"] = dict(ref.body_mapping(), reference_hash=ref.reference_hash)
        output["availability_assertion"] = plain(assertion)
        output["c2_context"] = plain(context)
        evaluator = trace.call("C2.Evaluator", native["Evaluator"])
        projection = trace.call("C2.Evaluator.project", evaluator.project,
                                catalog=ref, assertion=assertion, context=context)
        trace.call("C2.Projection.verify", projection.verify)
        output["c2_projection"] = plain(projection)
        need(projection.authority_granted is False and projection.execution_permitted is False and
             projection.candidate_planning_only is True, "CANDIDATE_BOUNDARY_VIOLATION", "C2")
        output.update(admission_candidate=ALIASES[projection.decision], stage="COMPLETE",
                      reason_codes=list(dict.fromkeys(validated["reason_codes"] + list(projection.reason_codes))))
        output["source_validation"]["recorded_native_calls"] = len(trace.events)
        return output
    except Exception as exc:
        if "source_validation" in output:
            output["source_validation"]["recorded_native_calls"] = len(trace.events)
        output["native_calls"] = trace.events
        cause = getattr(exc, "code", type(exc).__name__)
        raise NativeFailure(stage, output, type(exc).__name__, cause,
                            private_diagnostic(exc)) from exc
