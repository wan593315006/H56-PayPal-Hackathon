"""Entry point: `python -B -m app.main selfcheck`.

selfcheck answers one question — is this directory the package that was assembled? —
and answers it from bytes, not from a version string. Each check prints one line with
the measured value, so a failure says what it saw rather than that something is wrong.
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import hostproof, settings

LONG_PREFIX = "\\\\?\\"
EXPECTED_EXPORTS = ("Assertion", "Catalog", "Compiler", "Context", "Definition",
                    "Evaluator", "Fact", "History", "Provenance", "Reference",
                    "StateCompilationError", "VersionTuple", "native_hash")
COLD_START = """
import json
import sys
from pathlib import Path

core = Path(sys.argv[1])
sys.path.insert(0, str(core))
from offline_qualification_v1.core_bridge import load_core

native, receipt = load_core(core, sys.argv[2])
print(json.dumps({"exports": sorted(native), "receipt": receipt}, sort_keys=True))
"""


class SelfcheckError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def _long(path):
    text = str(path)
    return text if text.startswith(LONG_PREFIX) else LONG_PREFIX + text


def _walk_files(root):
    """Yield (posix relative path, long absolute path) for every file under root."""
    prefix = _long(root) + os.sep
    for base, _dirs, files in os.walk(prefix):
        for name in files:
            full = os.path.join(base, name)
            yield full[len(prefix):].replace(os.sep, "/"), full


def _read_manifest():
    """Read the shipped declaration without trusting it: hash first, then parse."""
    path = _long(settings.CORE_ROOT / settings.DECLARATION_PATH)
    with open(path, "rb") as handle:
        raw = handle.read()
    measured = hashlib.sha256(raw).hexdigest()
    if measured != settings.SOURCE_MANIFEST_SHA:
        raise SelfcheckError("SOURCE_MANIFEST_SHA", measured)
    document = json.loads(raw.decode("utf-8"))
    members = document.get("runtime_required")
    if not isinstance(members, list) or len(members) != settings.MEMBER_COUNT:
        raise SelfcheckError("SOURCE_MEMBER_COUNT", len(members or []))
    return members, len(raw)


def check_disk_set(members):
    """C1: the disk holds the 139 members plus the declaration, and nothing else."""
    expected = {m["path"] for m in members} | {settings.DECLARATION_PATH}
    actual = {rel for rel, _ in _walk_files(settings.CORE_ROOT)}
    extra, missing = sorted(actual - expected), sorted(expected - actual)
    detail = "files=%d expected=%d" % (len(actual), len(expected))
    if extra:
        detail += " extra=" + ",".join(extra[:3])
    if missing:
        detail += " missing=" + ",".join(missing[:3])
    return (not extra and not missing), detail


def check_source_identity():
    """C2: the kernel's own reader agrees on the product root and the 139 count."""
    from offline_qualification_v1.assets import source_manifest

    product, document = source_manifest(settings.SOURCE_MANIFEST_SHA)
    same_root = os.path.normcase(str(Path(product))) == os.path.normcase(str(settings.CORE_ROOT))
    count = len(document["runtime_required"])
    return (same_root and count == settings.MEMBER_COUNT), \
        "root_matches=%s members=%d" % (same_root, count)


def check_assets():
    """C3: the three fixed assets load, hash-check and satisfy their field contracts."""
    from offline_qualification_v1.assets import load_assets

    assets = load_assets(settings.ASSET_MANIFEST_SHA)
    names = sorted(k for k in assets if k in ("policy", "mapping", "capability"))
    role = assets["policy"]["role"]
    return (names == ["capability", "mapping", "policy"] and role == "SIMULATED_OPERATOR_METADATA_HOST"), \
        "assets=%s role=%s" % (",".join(names), role)


def check_tests():
    """C4: the 30 offline cases pass, with a scratch root created outside the package."""
    from offline_qualification_v1.tests import test_records

    previous = test_records.TEST_ROOT
    with tempfile.TemporaryDirectory(prefix="h56-selfcheck-") as scratch:
        test_records.TEST_ROOT = scratch
        try:
            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            for name in settings.TEST_MODULES:
                suite.addTests(loader.loadTestsFromName("offline_qualification_v1.tests." + name))
            cases = suite.countTestCases()
            stream = io.StringIO()
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
        finally:
            test_records.TEST_ROOT = previous
    ok = cases == 30 and not result.failures and not result.errors
    detail = "cases=%d failures=%d errors=%d skipped=%d" % (
        cases, len(result.failures), len(result.errors), len(result.skipped))
    if not ok:
        first = (result.failures + result.errors)
        if first:
            detail += " first=" + first[0][0].id().rsplit(".", 1)[-1]
    return ok, detail


def check_cold_start():
    """C5: a fresh interpreter imports the four native cores from pinned source bytes.

    Run in a child process so the result does not depend on what the test suite already
    imported. The child gets `-E` (no Python environment configuration), `-B` (no byte
    cache) and an allowlisted environment: inheriting the parent's environment would hand
    it credentials it has no use for.
    """
    environment = settings.subprocess_environment()
    finished = subprocess.run(
        [sys.executable, "-B", "-E", "-c", COLD_START,
         str(settings.CORE_ROOT), settings.SOURCE_MANIFEST_SHA],
        cwd=str(settings.PACKAGE_ROOT), env=environment, capture_output=True, text=True)
    if finished.returncode != 0:
        tail = (finished.stderr or "").strip().splitlines()
        raise SelfcheckError("NATIVE_COLD_START_FAILED", tail[-1][:200] if tail else "no stderr")
    line = [row for row in (finished.stdout or "").splitlines() if row.strip()][-1]
    payload = json.loads(line)
    exports = tuple(payload["exports"])
    receipt = payload["receipt"]
    ok = (exports == EXPECTED_EXPORTS and receipt["file_count"] == 110
          and receipt["source_commit"] == "9221e16460258bc81e1176d69f63a09f81159b73"
          and receipt["status"] == "SOURCE_IDENTITY_ONLY")
    return ok, "exports=%d vendor_files=%d commit=%s env_keys=%d" % (
        len(exports), receipt["file_count"], receipt["source_commit"][:8], len(environment))


def check_clean():
    """C6: running everything above left no byte cache behind."""
    caches = files = 0
    for rel, _full in _walk_files(settings.CORE_ROOT):
        parts = rel.split("/")
        if "__pycache__" in parts:
            caches += 1
        elif rel.endswith(".pyc"):
            files += 1
    return (caches == 0 and files == 0), "pycache=%d pyc=%d" % (caches, files)


CHECKS = (
    ("C1", "disk file set", check_disk_set),
    ("C2", "source identity", check_source_identity),
    ("C3", "fixed assets", check_assets),
    ("C4", "offline cases", check_tests),
    ("C5", "native cold start", check_cold_start),
    ("C6", "no byte cache", check_clean),
)


def selfcheck():
    members, declaration_bytes = _read_manifest()
    total = sum(m["size"] for m in members)
    print("package   %s" % settings.PACKAGE_ROOT)
    print("python    %s" % sys.version.split()[0])
    print("members   %d (%d B) + declaration %d B" % (
        len(members), total, declaration_bytes))
    print("-" * 62)
    sys.path.insert(0, str(settings.CORE_ROOT))
    # C1 is the only check that needs the parsed member list; bind it here so the rest of
    # the table stays a plain list of zero-argument callables.
    checks = [("C1", "disk file set", lambda: check_disk_set(members))]
    checks.extend(row for row in CHECKS if row[0] != "C1")
    passed = 0
    for code, label, check in checks:
        try:
            ok, detail = check()
        except SelfcheckError as error:
            ok, detail = False, "%s %s" % (error.code, error)
        except Exception as error:  # a raised error is a failed check, not a crash
            ok, detail = False, "%s: %s" % (type(error).__name__, str(error)[:160])
        passed += 1 if ok else 0
        print("%-4s %-3s %-18s %s" % ("PASS" if ok else "FAIL", code, label, detail))
    print("-" * 62)
    if passed == len(checks):
        print("SELFCHECK PASS %d/%d" % (passed, len(checks)))
        return 0
    print("SELFCHECK FAIL %d/%d" % (passed, len(checks)))
    return 1


EXIT_OK, EXIT_SELFCHECK, EXIT_USAGE, EXIT_BLOCKED, EXIT_KERNEL = 0, 1, 2, 3, 4
EXIT_BINDING = 5


def build_order(offer_id, offer, amount_minor=None, currency=None, payee=None):
    """An order is what the operator wants to pay; the catalogue is the price source.

    `offer` is None when the identifier is not in the catalogue. That case still builds an
    order: the policy layer is what must report the miss, so this function must not raise
    first and hide the rule that applies.

    `amount_source` records where the number came from. When the caller supplies nothing
    the catalogue is the server-side calculator and the value cannot disagree with itself;
    when the caller supplies a number it is marked as such and R4 compares it against the
    catalogue price. The field exists because "the amount was taken from the catalogue"
    and "the amount happened to match the catalogue" are different claims, and only the
    first one is true when the value is defaulted.
    """
    offer = offer or {}
    return {
        "offer_id": offer_id,
        "amount_minor": offer.get("amount_minor") if amount_minor is None else amount_minor,
        "currency": offer.get("currency") if currency is None else currency,
        "payee": offer.get("payee") if payee is None else payee,
        "amount_source": "CATALOGUE" if amount_minor is None else "CLIENT_SUPPLIED",
    }


def _print_policy(result):
    print("POLICY    %s reasons=%s" % (
        result["decision"], ",".join(result["reason_codes"]) or "-"))


def _write_blocked(run_directory, policy, order):
    """A business refusal is not a kernel record: it stays in the run directory."""
    document = {
        "schema": "H56_APP_RUN_RESULT_V1",
        "layer": "BUSINESS_POLICY",
        "decision": "BLOCKED",
        "reason_codes": list(policy["reason_codes"]),
        "rules": list(policy["rules"]),
        "order": order,
        "h56_invoked": False,
        "h56_status": "NOT_EVALUATED",
        "note": "H56 was not asked. This verdict is the application's, not the kernel's.",
    }
    run_directory.joinpath("result.json").write_bytes(
        hostproof.dumps(document).encode("utf-8"))
    return document


def evaluate_command(arguments):
    """One end-to-end offline run: catalogue, policy, host snapshot, four cores, binding."""
    from . import policy

    stamp = arguments.stamp or settings.utc_stamp()
    business = arguments.business
    run_directory = settings.run_directory(stamp, business)
    catalogue = policy.load_catalog()
    offer = next((o for o in catalogue["offers"] if o["offer_id"] == arguments.offer_id), None)
    order = build_order(arguments.offer_id, offer,
                        arguments.amount_minor, arguments.currency, arguments.payee)
    order["order_id"] = arguments.order_id

    verdict = policy.decide(order, catalogue)
    _print_policy(verdict)
    if verdict["decision"] != "ALLOW":
        document = _write_blocked(run_directory, verdict, order)
        print("H56       NOT_INVOKED h56_invoked=%s records_written=0" % (
            document["h56_invoked"]))
        print("RUN       %s" % run_directory.name)
        return EXIT_BLOCKED

    # Only now does the kernel become reachable: a business refusal above returns before
    # this line, so "the kernel was never asked" is a property of the code path, not a claim.
    from . import binding, h56bridge

    names = h56bridge.identifiers(business, stamp, host_key=arguments.host_key)
    task = h56bridge.task_ref(names["task_id"])
    # `--as-of` pins the snapshot moment so two runs can be compared field for field. It is
    # not a convenience flag: without it every evidence item carries a different
    # `observed_at`, and a "one field differs" claim becomes untestable by construction.
    as_of = arguments.as_of or hostproof.stamp(hostproof.utc_now())
    observed = (hostproof.stamp(hostproof.shift(hostproof.utc_now(),
                                                -arguments.observed_offset))
                if arguments.observed_offset else None)
    values = {"dependencies_available": arguments.dependencies == "true"}
    if arguments.integrity_rid is not None:
        values["integrity_rid"] = arguments.integrity_rid
    envelope, envelope_raw = hostproof.build(
        names["environment_id"], task, as_of, observed_at=observed, values=values)

    # The request identifier carries the order's fingerprint from here on. This is the only
    # place the order enters the request, and it enters by digest, not by text: the kernel
    # derives `assessment_id` from the digest of the whole request, so the recorded id is a
    # function of the order without the kernel knowing what an order is.
    request_id = binding.request_id_for(names["request_id"], order)

    try:
        request = h56bridge.request_document(
            request_id, task, names["environment_id"],
            hashlib.sha256(envelope_raw).hexdigest(), as_of)
        result = h56bridge.evaluate(envelope_raw, request, settings.RECORDS_ROOT,
                                    names["session"])
    except Exception as error:  # the kernel refuses by raising, not by returning
        code = getattr(error, "code", type(error).__name__)
        stage = getattr(error, "stage", "INPUT")
        document = {
            "schema": "H56_APP_RUN_RESULT_V1",
            "layer": "KERNEL",
            "decision": "REJECTED",
            "h56_invoked": True,
            "reason_codes": [code],
            "stage": stage,
            "request_id": request_id,
        }
        run_directory.joinpath("result.json").write_bytes(
            hostproof.dumps(document).encode("utf-8"))
        print("H56       REJECTED stage=%s code=%s" % (stage, code))
        print("RUN       %s" % run_directory.name)
        return EXIT_KERNEL

    record = binding.make(catalogue, order, request, envelope_raw, result["reference"],
                          names["session"])
    summary = h56bridge.summarize(result)
    summary.update(schema="H56_APP_RUN_RESULT_V1", layer="KERNEL", h56_invoked=True,
                   request_id=request_id, session=names["session"],
                   reference=result["reference"],
                   order=order, policy=dict(decision=verdict["decision"],
                                            reason_codes=verdict["reason_codes"]),
                   binding_sha256=record["binding_sha256"])
    h56bridge.write_run(run_directory, request, envelope_raw, summary, binding=record)
    print("H56       %s stage=%s native_calls=%d returned=%d evidence=%s policy=%s" % (
        summary["decision"], summary["stage"], summary["native_calls"],
        summary["native_returned"], summary["evidence_state"], summary["policy_state"]))
    print("ASSESS    %s" % summary["assessment_id"])
    print("DECISION  %s" % summary["decision_id"])
    print("BOUNDARY  authority_granted=%s execution_permitted=%s business_action_calls=%s" % (
        summary["authority_granted"], summary["execution_permitted"],
        summary["business_action_calls"]))
    print("BINDING   order_token=%s amount=%s(%s) binding_sha256=%s" % (
        record["order_token"], order["amount_minor"], order["amount_source"],
        record["binding_sha256"][:16]))
    print("RUN       %s" % run_directory.name)
    return EXIT_OK


def evaluate_parser(sub):
    parser = sub.add_parser(
        "evaluate", help="run one offline chain: policy, host proof, four cores, binding")
    parser.add_argument("--offer-id", required=True)
    parser.add_argument("--order-id", default="O-DEFAULT")
    parser.add_argument("--amount-minor", type=int, default=None)
    parser.add_argument("--currency", default=None)
    parser.add_argument("--payee", default=None)
    parser.add_argument("--business", default="shop")
    parser.add_argument("--stamp", default=None, help="20261103T021741Z; defaults to now")
    parser.add_argument("--dependencies", choices=("true", "false"), default="true",
                        help="the one fact the negative case flips")
    parser.add_argument("--integrity-rid", type=int, default=None)
    parser.add_argument("--observed-offset", type=int, default=0,
                        help="seconds to age the snapshot; >300 expires every field")
    parser.add_argument("--as-of", default=None,
                        help="pin the snapshot moment (2026-11-03T04:00:00Z); defaults to now")
    parser.add_argument("--host-key", default=None,
                        help="pin task and environment identity for a controlled comparison")
    return parser


def verify_command(arguments):
    """Re-check an existing run's binding without asking the kernel to decide again.

    Nothing here re-runs the four cores. The point is exactly that: the binding must be
    verifiable from the bytes on disk, so an auditor without a working kernel can still
    find out whether the order in `result.json` is the order this assessment was made for.
    """
    from . import binding, policy

    directory = settings.existing_run_directory(arguments.stamp, arguments.business)
    required = ("binding.json", "result.json", "request.json", "evidence.json")
    missing = [name for name in required if not directory.joinpath(name).is_file()]
    if missing:
        print("BINDING   REJECTED codes=BINDING_DOCUMENT_MISSING:%s" % ",".join(missing))
        print("BIND_FINDINGS=1")
        print("VERIFY_EXIT=%d" % EXIT_BINDING)
        return EXIT_BINDING

    read = lambda name: json.loads(directory.joinpath(name).read_bytes().decode("utf-8"))
    record = read("binding.json")
    result = read("result.json")
    request = read("request.json")
    evidence_raw = directory.joinpath("evidence.json").read_bytes()

    findings = binding.check(record, policy.load_catalog(),
                             result.get("order") or {}, request, evidence_raw)

    # The last link is the only one that cannot be recomputed from the run directory alone:
    # it asks the record store whether the assessment the binding names actually exists and
    # still hashes to what the event says. A binding that points at a deleted artifact is a
    # broken binding even if every digest in it is self-consistent.
    if not findings:
        from . import h56bridge
        try:
            store = h56bridge.kernel()[1].RecordStore(
                Path(settings.RECORDS_ROOT).absolute(), record["session"], create=False)
            store.view(record["reference"])
        except Exception as error:  # noqa: BLE001 - any refusal here is the finding
            findings.append("%s:%s" % (binding.ASSESSMENT_UNAVAILABLE,
                                       getattr(error, "code", type(error).__name__)))

    ok = not findings
    print("BINDING   %s codes=%s" % ("OK" if ok else "REJECTED", ",".join(findings) or "-"))
    print("BIND_FINDINGS=%d" % len(findings))
    print("VERIFY_EXIT=%d" % (EXIT_OK if ok else EXIT_BINDING))
    return EXIT_OK if ok else EXIT_BINDING


def verify_parser(sub):
    parser = sub.add_parser(
        "verify", help="re-check one run's order/kernel binding from its bytes")
    parser.add_argument("--stamp", required=True, help="20261103T035626Z")
    parser.add_argument("--business", default="shop")
    return parser


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="app.main", description="H56 PayPal submission package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selfcheck", help="verify the package against its own identity record")
    evaluate_parser(sub)
    verify_parser(sub)
    arguments = parser.parse_args(argv)
    if arguments.command == "selfcheck":
        return selfcheck()
    if arguments.command == "verify":
        return verify_command(arguments)
    if arguments.command == "evaluate":
        return evaluate_command(arguments)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
