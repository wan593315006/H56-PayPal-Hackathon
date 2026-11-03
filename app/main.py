"""Entry point: `python -B -m app.main selfcheck`.

selfcheck answers one question — is this directory the package that was assembled? —
and answers it from bytes, not from a version string. Each check prints one line with
the measured value, so a failure says what it saw rather than that something is wrong.
"""
import argparse
import datetime
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
EXIT_REPLAY = 6
EXIT_RECOVERY = 7
EXIT_SANDBOX = 8


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

    # The last two links need the record store: does the assessment still exist, and does
    # the verdict on display equal the verdict that was recorded. Opening the record and
    # throwing away what came back answers only the first -- which is how a result.json
    # whose decision had been edited still verified clean.
    #
    # Handing in the loader and nothing else matters: `binding.audit` owns the order of the
    # three layers and the decision to consult the store at all, and G1-11 calls the same
    # function with its own two-line loader. Anything the CLI decided here on its own would
    # be a second copy of that rule, free to drift from the gate that is supposed to prove it.
    def open_record(session, reference):
        from . import h56bridge
        store = h56bridge.kernel()[1].RecordStore(
            Path(settings.RECORDS_ROOT).absolute(), session, create=False)
        return store.view(reference)["record"]

    findings, kernel_record = binding.audit(record, policy.load_catalog(), result, request,
                                            evidence_raw, open_record)

    ok = not findings
    print("BINDING   %s codes=%s" % ("OK" if ok else "REJECTED", ",".join(findings) or "-"))
    print("BIND_RECORD %s" % ((kernel_record or {}).get("assessment_id") or "-"))
    print("BIND_FINDINGS=%d" % len(findings))
    print("VERIFY_EXIT=%d" % (EXIT_OK if ok else EXIT_BINDING))
    return EXIT_OK if ok else EXIT_BINDING


def verify_parser(sub):
    parser = sub.add_parser(
        "verify", help="re-check one run's order/kernel binding from its bytes")
    parser.add_argument("--stamp", required=True, help="20261103T035626Z")
    parser.add_argument("--business", default="shop")
    return parser


def replay_parser(sub):
    parser = sub.add_parser(
        "replay", help="re-submit one run's stored request and report whether it reused")
    parser.add_argument("--stamp", required=True, help="20261103T171000Z")
    parser.add_argument("--business", default="shop")
    return parser


def replay_command(arguments):
    """Submit the bytes already on disk again, and report what the kernel did with them.

    The point is not to compute anything. A successful replay must leave the journal byte
    for byte unchanged: that is what "the kernel returned its original record" looks like
    from outside. A second assessment, by contrast, appends an event, and that difference is
    the only reliable way to tell the two apart -- `native_recomputed` is written as False on
    every successful return, including a fresh computation, so it cannot be the judge.
    """
    from . import h56bridge

    try:
        directory = settings.existing_run_directory(arguments.stamp, arguments.business)
    except settings.RunPathError as error:
        # A missing directory is a refusal with a name, not a traceback. The earlier version
        # let it escape and exited 1 by crashing, which looks like success to a wrapper that
        # only checks "non-zero" and tells an operator nothing about what was missing.
        print("REPLAY    REFUSED code=%s" % error.code)
        print("REPLAY_STATE=%s" % error.code)
        print("REPLAY_EXIT=%d" % EXIT_REPLAY)
        return EXIT_REPLAY

    required = ("request.json", "evidence.json", "result.json")
    missing = [name for name in required if not directory.joinpath(name).is_file()]
    if missing:
        print("REPLAY    REFUSED code=REPLAY_DOCUMENT_MISSING:%s" % ",".join(missing))
        print("REPLAY_STATE=DOCUMENT_MISSING")
        print("REPLAY_EXIT=%d" % EXIT_REPLAY)
        return EXIT_REPLAY

    read = lambda name: json.loads(directory.joinpath(name).read_bytes().decode("utf-8"))
    request = read("request.json")
    result = read("result.json")
    evidence_raw = directory.joinpath("evidence.json").read_bytes()
    session = "oq_%s_%s" % (arguments.business, arguments.stamp)

    journal = Path(settings.RECORDS_ROOT) / session / "events.jsonl"
    before = journal.read_bytes() if journal.is_file() else b""

    try:
        replay = h56bridge.evaluate(evidence_raw, request, settings.RECORDS_ROOT, session)
    except Exception as error:  # noqa: BLE001 - a refusal is the finding, not a crash
        code = getattr(error, "code", None) or type(error).__name__
        print("REPLAY    REFUSED code=%s" % code)
        print("REPLAY_STATE=REFUSED")
        print("REPLAY_EXIT=%d" % EXIT_REPLAY)
        return EXIT_REPLAY

    after = journal.read_bytes() if journal.is_file() else b""
    original = (result.get("reference") or {}).get("assessment_id")
    same = replay["reference"]["assessment_id"] == original
    if after == before and same:
        state = "REUSED"
    elif len(after.splitlines()) > len(before.splitlines()):
        state = "RECOMPUTED"
    else:
        state = "DIFFERENT"

    print("REPLAY    %s assessment=%s" % (
        state, str(replay["reference"]["assessment_id"])[7:19]))
    print("REPLAY_EVENTS_BEFORE=%d" % len(before.splitlines()))
    print("REPLAY_EVENTS_AFTER=%d" % len(after.splitlines()))
    print("REPLAY_JOURNAL_UNCHANGED=%s" % (after == before))
    print("REPLAY_ASSESSMENT_SAME=%s" % same)
    print("REPLAY_STATE=%s" % state)
    print("REPLAY_EXIT=%d" % (EXIT_OK if state == "REUSED" else EXIT_REPLAY))
    return EXIT_OK if state == "REUSED" else EXIT_REPLAY


def recover_parser(sub):
    parser = sub.add_parser(
        "recover", help="classify the record store, or write recovery.json for one run")
    parser.add_argument("--survey", action="store_true",
                        help="classify every session and stop; writes nothing")
    parser.add_argument("--session", default=None, help="oq_shop_20261103T171000Z")
    parser.add_argument("--stamp", default=None, help="run stamp to place recovery.json in")
    parser.add_argument("--business", default="shop")
    parser.add_argument("--create-run", action="store_true",
                        help="create the run directory if it is gone, and say so in the file")
    return parser


def recover_command(arguments):
    """Two modes, both refusing to edit the record store.

    `--survey` reads and classifies. `--session` copies one surviving verdict into a new
    `recovery.json` beside its run. Neither mode deletes a claim, truncates a journal, or
    writes a `result.json` that would read like a first-hand summary.
    """
    from . import recovery

    if arguments.survey:
        rows = recovery.survey(settings.RECORDS_ROOT)
        print("%-18s %-11s %6s %9s %6s %8s" % (
            "state", "session", "claims", "artifacts", "events", "journalB"))
        print("-" * 66)
        for row in rows:
            print("%-18s %-11s %6d %9d %6d %8d" % (
                row["state"], row["session"][-11:], row["claims"], row["artifacts"],
                row["events"], row["journal_bytes"]))
        degraded = [row for row in rows if row["state"] != recovery.HEALTHY]
        print("-" * 66)
        for row in degraded:
            print("ADVICE %s: %s%s" % (
                row["session"], row["advice"],
                "" if not row["findings"] else " [%s]" % ",".join(sorted(set(row["findings"])))))
        print("SURVEY_SESSIONS=%d" % len(rows))
        print("SURVEY_HEALTHY=%d" % (len(rows) - len(degraded)))
        print("SURVEY_DEGRADED=%d" % len(degraded))
        print("SURVEY_CHAIN_BROKEN=%d" % sum(1 for row in rows
                                             if row["state"] == recovery.CHAIN_BROKEN))
        print("RECOVER_EXIT=0")
        return EXIT_OK

    if not arguments.session or not arguments.stamp:
        print("RECOVER   REFUSED code=RECOVER_ARGUMENTS (need --survey or --session+--stamp)")
        print("RECOVER_EXIT=%d" % EXIT_RECOVERY)
        return EXIT_RECOVERY

    created = False
    try:
        directory = settings.existing_run_directory(arguments.stamp, arguments.business)
    except settings.RunPathError as error:
        if error.code != "RUN_DIRECTORY_MISSING" or not arguments.create_run:
            print("RECOVER   REFUSED code=%s" % error.code)
            print("RECOVER_EXIT=%d" % EXIT_RECOVERY)
            return EXIT_RECOVERY
        directory = settings.run_directory(arguments.stamp, arguments.business)
        created = True

    # The kernel is the primary witness where it can still open the session. `recovery` does
    # not import it: a survey has to work on a store the kernel has already refused. So the
    # verifier is handed in here, and a refusal from it is a refusal from `restore`.
    def kernel_view(session, reference):
        from . import h56bridge
        store = h56bridge.kernel()[1].RecordStore(
            Path(settings.RECORDS_ROOT).absolute(), session, create=False)
        return store.view(reference)["record"]

    try:
        document, target = recovery.restore(settings.RECORDS_ROOT, arguments.session,
                                            directory, kernel_verifier=kernel_view)
    except recovery.RecoveryError as error:
        print("RECOVER   REFUSED code=%s detail=%s" % (error.code, str(error).split(": ")[-1]))
        print("RECOVER_EXIT=%d" % EXIT_RECOVERY)
        return EXIT_RECOVERY

    document["run_directory_created"] = created
    target.write_bytes(hostproof.dumps(document).encode("utf-8"))
    print("RECOVER   session=%s decision=%s calls=%d" % (
        arguments.session, document["decision"], document["native_calls"]))
    print("RECOVER_ORDER_RECOVERABLE=%s" % document["order_recoverable"])
    print("RECOVER_RUN_CREATED=%s" % created)
    print("RECOVER_KERNEL_CHECKED=%s" % document["verification"]["kernel_consulted"])
    print("RECOVER_EXIT=0")
    return EXIT_OK


def sandbox_parser(sub):
    parser = sub.add_parser(
        "sandbox", help="PayPal Sandbox order: plan, create, status, capture")
    parser.add_argument("--step", required=True, choices=("plan", "create", "status", "capture"))
    parser.add_argument("--offer-id", default="S-C01")
    parser.add_argument("--payee-email", default=None,
                        help="the sandbox business account the money must reach")
    parser.add_argument("--return-url", default="https://example.com/h56/sandbox/return")
    parser.add_argument("--cancel-url", default="https://example.com/h56/sandbox/cancel")
    parser.add_argument("--order-id", default=None,
                        help="the PayPal order id (needed by status and capture)")
    parser.add_argument("--stamp", default=None,
                        help="same stamp for evaluate, create and capture; defaults to now")
    parser.add_argument("--business", default="shop")
    return parser


def _intent_path(directory):
    return directory / "paypal" / "00_intent.json"


def _read_intent(directory):
    """The persisted operation state, or None when this flow has not started here.

    A directory that exists with an unparsable or keyless intent file is a state this
    flow cannot name, and proceeding would mean sending requests whose retry identity is
    unknown. It refuses instead: an unnamed state is not an empty one.
    """
    from . import sandbox
    path = _intent_path(directory)
    if not path.is_file():
        return None
    try:
        intent = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise sandbox.SandboxError(
            sandbox.RUN_STATE_UNKNOWN, "00_intent.json is not parsable") from None
    if not isinstance(intent, dict) or not intent.get("create_key"):
        raise sandbox.SandboxError(
            sandbox.RUN_STATE_UNKNOWN, "00_intent.json carries no create_key")
    return intent


def _write_intent(directory, intent):
    path = _intent_path(directory)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(hostproof.dumps(intent).encode("utf-8"))
    return path


def _h56_gate(stamp, business, order, catalogue, directory=None, records_root=None):
    """The three local legs of the execution gate, re-checked at the moment of execution.

    Four legs must hold before money moves, and the auditor measured what happens when
    they are not a conjunction: with a real INFEASIBLE record sitting in this very run
    directory, create and capture both reached the wire, and the binding was consulted
    zero times. The four legs are:

    * payment policy -- the catalogue admits this offer at this amount (settled by the
      caller, which builds the order from the catalogue rather than from a flag);
    * the H56 verdict -- read from the result this run wrote, never from a command line.
      A verdict a caller can type is not a verdict, it is a wish, and `--decision` is
      gone;
    * the binding -- `binding.audit` against the kernel's own record, run now, at
      execution time, not assumed from whenever the evaluation happened;
    * the buyer's approval -- PayPal's APPROVED, checked by the capture step, because it
      is PayPal's fact and no local record can stand in for it.

    Everything here is re-derivable from bytes on disk plus one kernel read, so the gate
    is cheap, and it runs on every execution step for exactly that reason.
    """
    from . import binding as app_binding, h56bridge, sandbox

    if directory is None:
        directory = settings.existing_run_directory(stamp, business)

    def read(name):
        path = directory / name
        if not path.is_file():
            raise sandbox.SandboxError(sandbox.H56_RECORD_MISSING, name)
        return path.read_bytes()

    try:
        result = json.loads(read("result.json").decode("utf-8"))
        request = json.loads(read("request.json").decode("utf-8"))
        binding_doc = json.loads(read("binding.json").decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise sandbox.SandboxError(
            sandbox.H56_RECORD_MISSING, "unreadable: %s" % type(error).__name__) from None
    evidence_raw = read("evidence.json")

    evaluated = result.get("order") or {}
    differing = [key for key in ("offer_id", "amount_minor", "currency", "payee")
                 if evaluated.get(key) != order.get(key)]
    if differing:
        raise sandbox.SandboxError(
            sandbox.H56_ORDER_MISMATCH,
            "%s: evaluated=%r execution=%r"
            % (",".join(differing), [evaluated.get(key) for key in differing],
               [order.get(key) for key in differing]))

    records = (Path(records_root) if records_root is not None
               else Path(settings.RECORDS_ROOT).absolute())

    def open_record(session, reference):
        store = h56bridge.kernel()[1].RecordStore(records, session, create=False)
        return store.view(reference)["record"]

    # The gate uses the same audit the verify command uses, and hands in only the
    # loader: when to consult the store and how a refusal becomes a code are decisions
    # that live in one place, because two copies of that rule is one copy edited alone.
    findings, kernel_record = app_binding.audit(
        binding_doc, catalogue, result, request, evidence_raw, open_record)
    if findings:
        raise sandbox.SandboxError(
            sandbox.H56_BINDING_INVALID,
            ",".join(item if isinstance(item, str) else "/".join(item)
                     for item in findings[:6]))

    decision = result.get("decision")
    if decision != "FEASIBLE":
        raise sandbox.SandboxError(
            sandbox.H56_DECISION_NOT_FEASIBLE, str(decision))

    as_of = request.get("as_of")
    try:
        moment = datetime.datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        raise sandbox.SandboxError(
            sandbox.H56_RECORD_MISSING, "request has no usable as_of") from None
    age = int((datetime.datetime.utcnow() - moment).total_seconds())
    if age > sandbox.MAX_EVALUATION_AGE_SECONDS:
        raise sandbox.SandboxError(
            sandbox.H56_EVALUATION_STALE, "as_of=%s age=%ds" % (as_of, age))

    return {"assessment_id": result.get("assessment_id"), "decision": decision,
            "as_of": as_of, "evaluation_age_seconds": age,
            "session": binding_doc.get("session"), "directory": directory,
            "kernel_record": kernel_record}


def _sandbox_write(directory, name, document):
    target = directory / "paypal"
    target.mkdir(exist_ok=True)
    path = target / name
    path.write_bytes(hostproof.dumps(document).encode("utf-8"))
    return path


def sandbox_command(arguments):
    """Four steps, and one conjunction that is not negotiable.

    `plan` reads nothing. `create` passes the H56 gate (offline, before the credentials
    are even read), proves the credentials, persists its intent with the idempotency key
    before sending, and reuses or reconciles on retry. `status` observes. `capture`
    passes the gate again, binds itself to the intent's order and assessment, verifies
    the order PayPal holds against the order this run decided on -- identity, amount,
    currency, payee, all before the capture request -- then requires APPROVED, then
    captures. A PENDING capture is reported as accepted-not-settled and exits non-zero.
    """
    from . import policy, sandbox

    catalogue = policy.load_catalog()
    offer = next((o for o in catalogue["offers"] if o["offer_id"] == arguments.offer_id), None)
    if offer is None:
        print("SANDBOX   REFUSED code=OFFER_UNKNOWN detail=%s" % arguments.offer_id)
        print("SANDBOX_EXIT=%d" % EXIT_USAGE)
        return EXIT_USAGE
    order = dict(offer_id=offer["offer_id"], description=offer["description"],
                 amount_minor=offer["amount_minor"], currency=offer["currency"],
                 payee=offer["payee"])
    stamp = arguments.stamp or settings.utc_stamp()

    try:
        base = sandbox.base_url()
        amount = sandbox.amount_value(order["amount_minor"])
        print("SANDBOX_STEP=%s" % arguments.step)
        print("SANDBOX_BASE=%s" % base)
        print("SANDBOX_AMOUNT=%s %s" % (order["currency"], amount))

        if arguments.step == "plan":
            if not arguments.payee_email:
                raise sandbox.SandboxError("SANDBOX_PAYEE_REQUIRED", "--payee-email")
            body = sandbox.create_body(order, arguments.payee_email,
                                       arguments.return_url, arguments.cancel_url)
            ledger = {}
            print("SANDBOX_INTENT=%s" % body["intent"])
            print("SANDBOX_PAYEE_REF=%s" % sandbox.redact(
                {"email_address": arguments.payee_email}, ledger)["email_address"])
            print("SANDBOX_CALLBACKS=%s|%s" % (body["application_context"]["return_url"],
                                               body["application_context"]["cancel_url"]))
            print("SANDBOX_BODY=%s" % sandbox.dumps(sandbox.redact(body)))
            print("SANDBOX_BODY_IS_REDACTED=True")
            print("SANDBOX_COMMIT_KEY_SEED=sha256(order_id,amount_minor,currency)")
            print("SANDBOX_TRANSPORT_CALLS=0")
            print("SANDBOX_NETWORK=not_used")
            print("SANDBOX_EXIT=0")
            return EXIT_OK

        transport = sandbox.LiveTransport(base)
        client = sandbox.SandboxClient(transport, base)

        if arguments.step == "create":
            if not arguments.payee_email:
                raise sandbox.SandboxError("SANDBOX_PAYEE_REQUIRED", "--payee-email")
            # The gate runs before anything else: offline, no credential read, no byte
            # sent. The auditor measured the previous order of operations -- a real
            # INFEASIBLE record in this very directory, and create reaching the wire with
            # the binding consulted zero times. Policy, verdict and binding are local
            # facts; they are settled before the credentials are even read.
            gate = _h56_gate(stamp, arguments.business, order, catalogue)
            client.token()
            payee_ref = sandbox.payee_ref(arguments.payee_email)
            create_key = sandbox.create_key(sandbox.create_seed(order, arguments.payee_email))
            # Reuse or create the run state, and never guess which. A directory without
            # an intent belongs to the evaluation that made it, and gains one now. A
            # directory whose intent already carries an order id is a create that may
            # have completed before its process died: reconciliation asks PayPal rather
            # than creating again, because with the idempotency key the second create
            # would be safe but the question "what did the first one do" would stay open.
            try:
                directory = settings.existing_run_directory(stamp, arguments.business)
            except settings.RunPathError:
                directory = settings.run_directory(stamp, arguments.business)
                intent = None
            else:
                intent = _read_intent(directory)
            if intent is not None and intent.get("order_id"):
                view = client.read_order(intent["order_id"])
                sandbox.verify_order(view, intent["order_id"], order, payee_ref)
                document = {
                    "schema": sandbox.SCHEMA, "step": "reconcile",
                    "stamp": stamp, "business": arguments.business,
                    "create_key": intent["create_key"], "order_id": intent["order_id"],
                    "response": view,
                    "h56": {"assessment_id": gate["assessment_id"],
                            "decision": gate["decision"]},
                }
                path = _sandbox_write(directory, "04_reconcile.json", document)
                print("SANDBOX_RECONCILED=True")
                print("SANDBOX_ORDER_ID=%s" % view["order_id"])
                print("SANDBOX_PAYPAL_STATUS=%s" % view["status"])
                print("SANDBOX_CREATE_KEY=%s" % intent["create_key"])
                print("SANDBOX_TRANSPORT_CALLS=%d" % len(transport.calls))
                print("SANDBOX_EVIDENCE=%s" % path)
                print("SANDBOX_EXIT=0")
                return EXIT_OK
            if intent is None:
                # The intent is on disk before the send: key, amount, payee reference and
                # state. A timeout or a crash after this point leaves enough behind to
                # name the operation, reuse its key, and ask what happened -- which is
                # the whole difference between a retry and a second order.
                intent = {
                    "schema": sandbox.SCHEMA, "step": "create", "state": "PENDING_SEND",
                    "create_key": create_key,
                    "offer_id": order["offer_id"], "amount_minor": order["amount_minor"],
                    "currency": order["currency"], "payee_ref": payee_ref,
                    "request": sandbox.redact(sandbox.create_body(
                        order, arguments.payee_email, arguments.return_url,
                        arguments.cancel_url)),
                    "assessment_id": gate["assessment_id"], "h56_decision": gate["decision"],
                }
                _write_intent(directory, intent)
            view = client.create_order(order, arguments.payee_email,
                                       arguments.return_url, arguments.cancel_url,
                                       request_id=create_key)
            intent["state"] = "ORDER_CREATED"
            intent["order_id"] = view["order_id"]
            _write_intent(directory, intent)
            document = {
                "schema": sandbox.SCHEMA, "interface": sandbox.INTERFACE,
                "step": "create", "stamp": stamp, "business": arguments.business,
                "base": base,
                "request": sandbox.redact(sandbox.create_body(
                    order, arguments.payee_email, arguments.return_url, arguments.cancel_url)),
                "response": view,
                "create_key": create_key,
                "token_realm": client.realm(),
                "h56": {"assessment_id": gate["assessment_id"], "decision": gate["decision"]},
                "authority_granted": False,
                "note": ("The buyer has not acted yet. `authority_granted` stays False until "
                         "PayPal reports APPROVED, whatever H56 decided."),
            }
            path = _sandbox_write(directory, "01_create_order.json", document)
            print("SANDBOX_ORDER_ID=%s" % view["order_id"])
            print("SANDBOX_STATUS=%s" % view["status"])
            print("SANDBOX_APPROVE_URL=%s" % (view["approve_url"] or "-"))
            print("SANDBOX_H56_DECISION=%s" % gate["decision"])
            print("SANDBOX_ASSESSMENT=%s" % gate["assessment_id"])
            print("SANDBOX_CREATE_KEY=%s" % create_key)
            print("SANDBOX_AUTHORITY_GRANTED=False")
            print("SANDBOX_TRANSPORT_CALLS=%d" % len(transport.calls))
            print("SANDBOX_EVIDENCE=%s" % path)
            print("SANDBOX_EXIT=0")
            return EXIT_OK

        if not arguments.order_id:
            raise sandbox.SandboxError("SANDBOX_ORDER_ID_REQUIRED", "--order-id")

        # The capture path re-walks every local leg. The gate comes first, then the
        # intent -- which is what binds this capture to the create this flow made, to
        # this order id, and to this assessment -- and only then the network.
        directory = settings.existing_run_directory(stamp, arguments.business)
        gate = _h56_gate(stamp, arguments.business, order, catalogue, directory=directory)
        intent = _read_intent(directory)
        if not intent or not intent.get("order_id"):
            raise sandbox.SandboxError(
                sandbox.RUN_STATE_UNKNOWN, "capture needs a create this flow recorded")
        if intent["order_id"] != arguments.order_id:
            raise sandbox.SandboxError(
                sandbox.ORDER_MISMATCH,
                "intent order_id=%s, requested=%s" % (intent["order_id"], arguments.order_id))
        if intent.get("assessment_id") and intent["assessment_id"] != gate["assessment_id"]:
            raise sandbox.SandboxError(
                sandbox.H56_ORDER_MISMATCH, "the assessment moved between create and capture")

        view = client.read_order(arguments.order_id)
        print("SANDBOX_PAYPAL_STATUS=%s" % view["status"])
        print("SANDBOX_PAYER_REF=%s" % (view["payer_ref"] or "-"))

        if arguments.step == "status":
            document = {"schema": sandbox.SCHEMA, "step": "status",
                        "order_id": arguments.order_id, "response": view,
                        "h56": {"assessment_id": gate["assessment_id"],
                                "decision": gate["decision"]},
                        "authority_granted": view["status"] == sandbox.APPROVED}
            path = _sandbox_write(directory, "02_order_state.json", document)
            print("SANDBOX_AUTHORITY_GRANTED=%s" % document["authority_granted"])
            print("SANDBOX_TRANSPORT_CALLS=%d" % len(transport.calls))
            print("SANDBOX_EVIDENCE=%s" % path)
            print("SANDBOX_EXIT=0")
            return EXIT_OK

        # capture. Identity, money and payee are checked against what PayPal actually
        # holds, before the capture request exists -- the auditor measured the previous
        # order: a wrong amount reported after the capture had gone out, a wrong payee
        # reported never.
        sandbox.verify_order(view, arguments.order_id, order, intent.get("payee_ref"))
        state = sandbox.capture_preconditions(view)
        print("SANDBOX_PRECONDITION=%s" % state)
        print("SANDBOX_H56_DECISION=%s" % gate["decision"])
        if state == sandbox.ALREADY_CAPTURED:
            print("SANDBOX_ALREADY_CAPTURED=True")
            print("SANDBOX_NOTE=order was already captured; nothing was charged again")
            print("SANDBOX_EXIT=0")
            return EXIT_OK
        seed = sandbox.commit_seed(arguments.order_id, order["amount_minor"], order["currency"])
        captured = client.capture_order(arguments.order_id, seed,
                                        order["amount_minor"], order["currency"])
        settled = captured["capture_status"] == sandbox.COMPLETED
        document = {"schema": sandbox.SCHEMA, "step": "capture",
                    "order_id": arguments.order_id, "capture": captured,
                    "commit_key": sandbox.commit_key(seed),
                    "settled": settled, "capture_state": captured["capture_status"],
                    "h56": {"assessment_id": gate["assessment_id"],
                            "decision": gate["decision"]},
                    "authority_granted": True,
                    "note": ("Capture proceeded only because PayPal reported APPROVED and "
                             "the H56 gate held. A PENDING capture is an accepted request, "
                             "not money that moved.")}
        path = _sandbox_write(directory, "03_capture.json", document)
        print("SANDBOX_CAPTURE_ID=%s" % captured["capture_id"])
        print("SANDBOX_CAPTURE_STATE=%s" % captured["capture_status"])
        print("SANDBOX_SETTLED=%s" % settled)
        if settled:
            print("SANDBOX_CAPTURED=%s %s" % (captured["currency"], captured["value"]))
            print("SANDBOX_FEE=%s %s" % (captured["fee_currency"], captured["fee_value"]))
            print("SANDBOX_NET=%s %s" % (captured["net_currency"], captured["net_value"]))
        else:
            print("SANDBOX_NOTE=PayPal accepted the capture request; it has not confirmed "
                  "that money moved, and this exit is not a completed payment")
        print("SANDBOX_COMMIT_KEY=%s" % sandbox.commit_key(seed))
        print("SANDBOX_TRANSPORT_CALLS=%d" % len(transport.calls))
        print("SANDBOX_EVIDENCE=%s" % path)
        if not settled:
            print("SANDBOX_EXIT=%d" % EXIT_SANDBOX)
            return EXIT_SANDBOX
        print("SANDBOX_EXIT=0")
        return EXIT_OK

    except settings.MissingCredentials as error:
        # Names only. The values were never read, so there is nothing to leak here.
        print("SANDBOX   REFUSED code=SANDBOX_CREDENTIALS_MISSING names=%s"
              % ",".join(error.names))
        print("SANDBOX_EXIT=%d" % EXIT_SANDBOX)
        return EXIT_SANDBOX
    except settings.RunPathError as error:
        print("SANDBOX   REFUSED code=%s" % error.code)
        print("SANDBOX_EXIT=%d" % EXIT_SANDBOX)
        return EXIT_SANDBOX
    except sandbox.SandboxError as error:
        print("SANDBOX   REFUSED code=%s detail=%s" % (error.code, error.detail[:160]))
        print("SANDBOX_EXIT=%d" % EXIT_SANDBOX)
        return EXIT_SANDBOX


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="app.main", description="H56 PayPal submission package")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selfcheck", help="verify the package against its own identity record")
    evaluate_parser(sub)
    verify_parser(sub)
    replay_parser(sub)
    recover_parser(sub)
    sandbox_parser(sub)
    arguments = parser.parse_args(argv)
    if arguments.command == "selfcheck":
        return selfcheck()
    if arguments.command == "verify":
        return verify_command(arguments)
    if arguments.command == "replay":
        return replay_command(arguments)
    if arguments.command == "recover":
        return recover_command(arguments)
    if arguments.command == "evaluate":
        return evaluate_command(arguments)
    if arguments.command == "sandbox":
        return sandbox_command(arguments)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
