"""The offline chain, pinned: one positive run, one negative run, one refusal, six bad inputs.

Every assertion here is a pair — a decision *and* the reason code that produced it. A test
that only checks `decision == "INFEASIBLE"` passes for an implementation that is infeasible
for the wrong reason, which is the failure mode worth guarding against.

Timestamps are fixed rather than read from the clock, so a rerun next month produces the
same digests. The one case that needs an expired snapshot moves a single item's timestamp
back by 301 seconds: the window is 300, so the field is voided and the verdict degrades —
that is not a rejection, and the two must not be described with the same word.

Record roots are temporary directories outside the package: a test run must not add files
to `records/`, because that directory is evidence, not scratch space.
"""
import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import h56bridge, hostproof, policy                     # noqa: E402

AS_OF = "2026-11-03T04:00:00Z"
EXPIRED = "2026-11-03T03:54:59Z"      # 301 seconds before AS_OF; the window is 300
BUSINESS = "t"

# The complete set of module names `app/` may import. Offline means offline: an entry added
# here is a deliberate decision that the package still runs with zero third-party wheels.
ALLOWED_IMPORTS = frozenset((
    "argparse", "datetime", "hashlib", "io", "json", "os", "pathlib", "re",
    "subprocess", "sys", "tempfile", "time", "unittest", "app",
    "offline_qualification_v1",
))

# The package was offline until P3. Rather than widening the set above -- which would let
# any module in `app/` open a socket and leave nothing to notice -- the network capability
# is confined to a declared, closed set of files, and the confinement is what the tests
# below assert. P4 added the AI proposal node as the second declared network consumer: a
# live model call is the one thing that module exists to do, and keeping it in its own
# file keeps the rest of the package provably socket-free.
NETWORK_IMPORTS = frozenset(("base64", "socket", "urllib"))
NETWORK_MODULES = frozenset(("sandbox.py", "proposal_ai.py"))
SANDBOX_IMPORTS = ALLOWED_IMPORTS | NETWORK_IMPORTS
# Only the command layer may reach the network module: a second importer would be a second
# place where an order can be placed. The same confinement applies to the AI node.
SANDBOX_CALLERS = frozenset(("main.py",))
AI_NODE_CALLERS = frozenset(("main.py",))


def names_for(tag):
    return h56bridge.identifiers(BUSINESS, tag)


def build(tag, values=None, coverage=None, observed_at=None):
    names = names_for(tag)
    task = h56bridge.task_ref(names["task_id"])
    envelope, raw = hostproof.build(names["environment_id"], task, AS_OF,
                                    observed_at=observed_at, values=values,
                                    coverage=coverage)
    return names, task, envelope, raw


def run(root, tag, mutate=None, values=None, coverage=None, observed_at=None):
    """One full chain. `mutate` edits the envelope after it is built, for the bad inputs."""
    names, task, envelope, raw = build(tag, values, coverage, observed_at)
    if mutate is not None:
        mutate(envelope)
        raw = hostproof.encode(envelope)
    request = h56bridge.request_document(
        names["request_id"], task, names["environment_id"],
        hashlib.sha256(raw).hexdigest(), AS_OF)
    return h56bridge.evaluate(raw, request, root, names["session"]), envelope, raw


class ChainTest(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="h56-p1-")
        self.root = Path(self._scratch.name) / "records"
        self.root.mkdir()

    def tearDown(self):
        self._scratch.cleanup()

    # G1-1, G1-2, G1-9 ---------------------------------------------------------------
    def test_positive_is_feasible_with_twenty_two_native_calls(self):
        result, _envelope, _raw = run(self.root, "pos01")
        record = result["record"]
        projection = record["c2_projection"]
        self.assertEqual(projection["decision"], "FEASIBLE")
        self.assertIn("DECLARED_CANDIDATE_FEASIBILITY_MATCH", record["reason_codes"])
        self.assertEqual(record["stage"], "COMPLETE")

        calls = record["mapping_trace"]["native_calls"]
        self.assertEqual(len(calls), 22)
        self.assertEqual([call["ordinal"] for call in calls], list(range(1, 23)))
        self.assertEqual({call["status"] for call in calls}, {"RETURNED"})
        # MAPPING is pure Python and contributes no call: 6 + 4 + 6 + 0 + 6 = 22.
        prefixes = [call["call"].split(".", 1)[0] for call in calls]
        self.assertEqual(prefixes.count("K0"), 6)
        self.assertEqual(prefixes.count("K1"), 4)
        self.assertEqual(prefixes.count("C1"), 6)
        self.assertEqual(prefixes.count("C2"), 6)

        boundary = record["boundary"]
        self.assertEqual(boundary["business_action_calls"], 0)
        self.assertFalse(boundary["authority_granted"])
        self.assertFalse(boundary["execution_permitted"])
        self.assertTrue(result["integrity_checked"])

        # G1-9: the store can replay its own record from the artifact bytes alone.
        replay = h56bridge.open_store(self.root, names_for("pos01")["session"]).view(
            result["reference"])
        self.assertEqual(replay["record"], record)
        self.assertTrue(replay["integrity_checked"])

    def test_serialiser_matches_the_kernel(self):
        _names, _task, envelope, _raw = build("ser01")
        request = h56bridge.request_document("req_ser01", _task, _names["environment_id"],
                                             "0" * 64, AS_OF)
        self.assertEqual(hostproof.dumps(envelope), h56bridge.check_canonical(envelope))
        self.assertEqual(hostproof.dumps(request), h56bridge.check_canonical(request))

    # G1-3 ---------------------------------------------------------------------------
    def test_flipping_one_fact_flips_the_verdict(self):
        passing, pass_envelope, _ = run(self.root, "neg01")
        failing, fail_envelope, _ = run(self.root, "neg02",
                                        values={"dependencies_available": False})
        self.assertEqual(passing["record"]["c2_projection"]["decision"], "FEASIBLE")
        projection = failing["record"]["c2_projection"]
        self.assertEqual(projection["decision"], "INFEASIBLE")
        self.assertIn("DECLARED_POLICY_DENIED", failing["record"]["reason_codes"])
        self.assertIn("ENV_DEPENDENCY_UNAVAILABLE", failing["record"]["reason_codes"])

        # Exactly one item differs, so the verdict change has exactly one available cause.
        differing = [(a, b) for a, b in zip(pass_envelope["items"], fail_envelope["items"])
                     if a != b]
        self.assertEqual(len(differing), 1)
        self.assertEqual(differing[0][0]["field"], "dependencies_available")
        self.assertEqual((differing[0][0]["value"], differing[0][1]["value"]), (True, False))

    # G1-6 ---------------------------------------------------------------------------
    def test_replay_returns_the_same_record_without_recomputing(self):
        first, envelope, raw = run(self.root, "idem01")
        second = run(self.root, "idem01")[0]
        self.assertEqual(first["record"]["assessment_id"], second["record"]["assessment_id"])
        self.assertEqual(first["record"]["decision_id"], second["record"]["decision_id"])
        self.assertFalse(second["native_recomputed"])
        artifacts = list((self.root / names_for("idem01")["session"] / "artifacts").iterdir())
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         first["record"]["raw_evidence_sha256"])
        self.assertEqual(json.loads(artifacts[0].read_bytes()),
                         json.loads(hostproof.dumps(first["record"])))

    # G1-4 ---------------------------------------------------------------------------
    def test_business_refusal_never_reaches_the_kernel(self):
        catalogue = policy.load_catalog()
        offer = catalogue["offers"][0]
        for order, code in (
                (dict(offer_id=offer["offer_id"], amount_minor=catalogue["per_order_limit_minor"] + 1,
                      currency=offer["currency"], payee=offer["payee"]),
                 "POLICY_AMOUNT_LIMIT_EXCEEDED"),
                (dict(offer_id="S-NOT-THERE", amount_minor=100,
                      currency=offer["currency"], payee=offer["payee"]),
                 "POLICY_OFFER_NOT_IN_CATALOG"),
                (dict(offer_id=offer["offer_id"], amount_minor=offer["amount_minor"],
                      currency=offer["currency"], payee="SOMEONE-ELSE"),
                 "POLICY_PAYEE_NOT_ALLOWED"),
                (dict(offer_id=offer["offer_id"], amount_minor=offer["amount_minor"],
                      currency="EUR", payee=offer["payee"]),
                 "POLICY_CURRENCY_MISMATCH")):
            verdict = policy.decide(order, catalogue)
            self.assertEqual(verdict["decision"], "BLOCKED")
            self.assertIn(code, verdict["reason_codes"])
        self.assertEqual(len(policy.decide(
            dict(offer_id=offer["offer_id"], amount_minor=offer["amount_minor"],
                 currency=offer["currency"], payee=offer["payee"]), catalogue)["reason_codes"]), 0)
        # A refusal is renewable evidence that nothing was written: the root is still empty.
        self.assertEqual(list(self.root.iterdir()), [])

    def test_catalogue_refuses_a_float_amount(self):
        with tempfile.TemporaryDirectory(prefix="h56-cat-") as scratch:
            path = Path(scratch) / "catalog.json"
            document = json.loads(policy.CATALOG_PATH.read_text(encoding="utf-8"))
            document["offers"][0]["amount_minor"] = 12.5
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(policy.PolicyError) as caught:
                policy.load_catalog(path)
            self.assertEqual(caught.exception.code, "CATALOG_AMOUNT_MUST_BE_INTEGER")

    # G1-5: five refusals, one degradation -------------------------------------------
    def test_extra_envelope_key_is_refused(self):
        def mutate(envelope):
            envelope["biz_id"] = "shop"          # the field the old plan invented
        with self.assertRaises(Exception) as caught:
            run(self.root, "bad01", mutate=mutate)
        self.assertEqual(getattr(caught.exception, "code", None), "ENV_INPUT_REJECTED")

    def test_missing_item_key_is_refused(self):
        def mutate(envelope):
            del envelope["items"][0]["coverage"]
        with self.assertRaises(Exception) as caught:
            run(self.root, "bad02", mutate=mutate)
        self.assertEqual(getattr(caught.exception, "code", None), "ENV_INPUT_REJECTED")

    def test_two_items_for_one_field_conflict(self):
        def mutate(envelope):
            twin = dict(envelope["items"][0])
            twin["evidence_id"] = "EV99_duplicate"
            envelope["items"].append(twin)
        with self.assertRaises(Exception) as caught:
            run(self.root, "bad03", mutate=mutate)
        self.assertEqual(getattr(caught.exception, "code", None), "ENV_EVIDENCE_CONFLICT")

    def test_float_value_is_refused_at_parse_not_at_structure(self):
        def mutate(envelope):
            envelope["items"][0]["value"] = 100.5
        with self.assertRaises(Exception) as caught:
            run(self.root, "bad04", mutate=mutate)
        self.assertEqual(getattr(caught.exception, "code", None), "ENV_INPUT_REJECTED")

        # The same bytes are valid JSON: the refusal comes from `parse_float`, not syntax.
        names, task, envelope, _raw = build("bad05")
        envelope["items"][0]["value"] = 100.5
        raw = hostproof.encode(envelope)
        self.assertEqual(json.loads(raw)["items"][0]["value"], 100.5)
        request = h56bridge.request_document(
            names["request_id"], task, names["environment_id"],
            hashlib.sha256(raw).hexdigest(), AS_OF)
        with self.assertRaises(Exception) as strict:
            h56bridge.evaluate(raw, request, self.root, names["session"])
        self.assertEqual(getattr(strict.exception, "code", None), "ENV_INPUT_REJECTED")

    def test_integrity_rid_outside_the_enum_is_refused(self):
        def mutate(envelope):
            envelope["items"][1]["value"] = 9000
        with self.assertRaises(Exception) as caught:
            run(self.root, "bad06", mutate=mutate)
        self.assertEqual(getattr(caught.exception, "code", None), "ENV_INPUT_REJECTED")

    def test_expired_field_degrades_the_verdict_instead_of_refusing(self):
        def mutate(envelope):
            for item in envelope["items"]:
                if item["field"] == "dependencies_available":
                    item["observed_at"] = EXPIRED
        result, _envelope, _raw = run(self.root, "bad07", mutate=mutate)
        record = result["record"]
        projection = record["c2_projection"]
        # Measured, not assumed: a voided field makes the AND expression unknown, so the
        # evaluator stops at "policy context not evidenced" (DEFER) before it ever reaches
        # "evidence requirement not satisfied" (NEED_MORE_EVIDENCE).
        self.assertEqual(projection["decision"], "DEFER")
        self.assertIn("POLICY_CONTEXT_NOT_EVIDENCED", record["reason_codes"])
        self.assertIn("ENV_EVIDENCE_EXPIRED", record["reason_codes"])
        self.assertEqual(record["c2_context"]["policy_state"], "DECLARED_UNKNOWN")
        self.assertEqual(record["c2_context"]["evidence_state"], "INSUFFICIENT")

    # G1-7 ---------------------------------------------------------------------------
    def _imports(self, path):
        """Absolute import roots: the shape the original gate was written against."""
        found = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".", 1)[0])
        return found

    def _siblings(self, path):
        """Sibling modules pulled in with `from . import x` -- a relative import has no root."""
        found = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and not node.module:
                for alias in node.names:
                    found.add(alias.name.split(".", 1)[0])
        return found

    def test_app_imports_only_the_standard_library_and_the_kernel(self):
        """Every module keeps the offline set; the declared network modules get the trio."""
        offenders = {}
        for path in sorted((ROOT / "app").glob("*.py")):
            allowed = SANDBOX_IMPORTS if path.name in NETWORK_MODULES else ALLOWED_IMPORTS
            for root in sorted(self._imports(path)):
                if root not in allowed:
                    offenders.setdefault(root, set()).add(path.name)
        self.assertEqual(offenders, {})

    def test_network_imports_stay_inside_the_declared_modules(self):
        """Outside the declared network modules, the trio is still a defect."""
        spread = {}
        for path in sorted((ROOT / "app").glob("*.py")):
            if path.name in NETWORK_MODULES:
                continue
            for root in sorted(self._imports(path) & NETWORK_IMPORTS):
                spread.setdefault(root, set()).add(path.name)
        self.assertEqual(spread, {})

    def test_only_the_command_layer_imports_the_network_module(self):
        """`main.py` wires the commands; nothing else may start an order."""
        callers = {path.name for path in sorted((ROOT / "app").glob("*.py"))
                   if path.name not in NETWORK_MODULES and "sandbox" in self._siblings(path)}
        self.assertEqual(callers, set(SANDBOX_CALLERS))

    def test_only_the_command_layer_imports_the_ai_node(self):
        """`main.py` wires propose-ai; nothing else may reach the model transport."""
        callers = {path.name for path in sorted((ROOT / "app").glob("*.py"))
                   if path.name not in NETWORK_MODULES
                   and "proposal_ai" in self._siblings(path)}
        self.assertEqual(callers, set(AI_NODE_CALLERS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
