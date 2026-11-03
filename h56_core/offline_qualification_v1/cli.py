"""Explicit operator-bound offline entry. No spawn, collector, or execution."""
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    # Anchor only this same product, no cwd/neighbor fallback.
    sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
    __package__ = "offline_qualification_v1"

import argparse
from pathlib import Path
from runtime_windows.errors import PreparationError
from .assets import read_bytes
from .contracts import canonical, decode, disjoint_roots, exact, need, raw_sha, sha
from .records import RecordStore

def emit_private_diagnostic(value):
    import sys
    raw = canonical(value).encode("utf-8")
    if len(raw) > 65536:
        value = dict(scope="PRIVATE_RAW_EXCEPTION_NOT_SEMANTIC", truncated=True,
                     raw_prefix_utf8=raw[:32768].decode("utf-8", "ignore"))
    sys.stderr.write(canonical(value) + "\n")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Synthetic candidate qualification only")
    parser.add_argument("operation", choices=("evaluate", "view"))
    parser.add_argument("--binding", required=True)
    parser.add_argument("--binding-sha256", required=True)
    args = parser.parse_args(argv)
    # This external hash is an operator/run-binding anchor, not a Human signature.
    raw = read_bytes(Path(args.binding))
    need(raw_sha(raw) == sha(args.binding_sha256), "RUN_BINDING_IDENTITY_MISMATCH")
    binding = decode(raw)
    exact(binding, ("schema", "operation", "input_root", "output_root", "session",
                    "request_sha256", "evidence_sha256", "source_manifest_sha256",
                    "asset_manifest_sha256", "reference"))
    need(binding["schema"] == "H56_OFFLINE_OPERATION_BINDING_V1" and
         binding["operation"] == args.operation, "RUN_BINDING_OPERATION_MISMATCH")
    from runtime_windows.source_identity import _root
    inputs, output = _root(Path(binding["input_root"])), _root(Path(binding["output_root"]))
    product = Path(__file__).absolute().parent.parent
    need(disjoint_roots(inputs, output, product), "RUN_ROOT_OVERLAP")
    if args.operation == "view":
        store = RecordStore(output, binding["session"], create=False)
        result = store.view(binding["reference"])
    else:
        from .assessment import evaluate
        raw_request = read_bytes(inputs / "request.json", maximum=262144)
        raw_evidence = read_bytes(inputs / "evidence.json", maximum=262144)
        need(raw_sha(raw_request) == sha(binding["request_sha256"]) and
             raw_sha(raw_evidence) == sha(binding["evidence_sha256"]), "ENV_INPUT_HASH_MISMATCH")
        req = decode(raw_request)
        need(req["source_manifest_sha256"] == binding["source_manifest_sha256"] and
             req["asset_manifest_sha256"] == binding["asset_manifest_sha256"] and
             req["raw_evidence_sha256"] == binding["evidence_sha256"], "RUN_BINDING_IDENTITY_MISMATCH")
        store = RecordStore(output, binding["session"], create=True)
        result = evaluate(raw_evidence, req, store)
    diagnostic = result.pop("transport_diagnostic", None)
    if diagnostic is not None:
        emit_private_diagnostic(diagnostic)
    print(canonical(result))
    return 21 if result["record"]["failure"] is not None else 0

if __name__ == "__main__":
    from .contracts import Rejected, canonical
    from .assessment import DiagnosticCommitFailure
    try:
        code = main()
    except DiagnosticCommitFailure as exc:
        from .core_bridge import private_diagnostic
        emit_private_diagnostic(dict(native_failure=exc.native_diagnostic,
                                     persistence_failure=private_diagnostic(exc)))
        print(canonical(dict(status="STOPPED", stage=exc.stage, reason=exc.code,
                             authority_granted=False, execution_permitted=False)))
        code = 22
    except Rejected as exc:
        from .core_bridge import private_diagnostic
        emit_private_diagnostic(private_diagnostic(exc))
        print(canonical(dict(status="STOPPED", stage=exc.stage, reason=exc.code,
                             authority_granted=False, execution_permitted=False)))
        code = (22 if exc.stage == "RECORD" else 23 if "BUDGET" in exc.code else
                21 if exc.stage == "SOURCE" or "SOURCE_OR_VERSION" in exc.code else 20)
    except PreparationError as exc:
        from .core_bridge import private_diagnostic
        emit_private_diagnostic(private_diagnostic(exc))
        print(canonical(dict(status="STOPPED", stage="SOURCE", reason=exc.code,
                             authority_granted=False, execution_permitted=False)))
        code = 21
    except (OSError, ValueError, KeyError) as exc:
        from .core_bridge import private_diagnostic
        emit_private_diagnostic(private_diagnostic(exc))
        print(canonical(dict(status="STOPPED", reason="OPERATION_FAILED",
                             exception_type=type(exc).__name__,
                             authority_granted=False, execution_permitted=False)))
        code = 22
    raise SystemExit(code)
