"""P1.2: the catalogue is the price, and an order is bound to exactly one assessment.

Three groups, each guarding a claim that was true of the code's intent but not of its
behaviour before this revision:

* the amount must *equal* the catalogue price, not merely sit under the order limit;
* an order must be bound to the assessment made for it, so editing the order or pairing
  it with an older assessment is refused;
* the single-variable contrast must differ in one evidence field and nothing else — same
  task identity, same environment identity, only the request identifier moving.

Each group has a passing case next to the refusals. A suite that only proves "bad input is
rejected" is satisfied by an implementation that rejects everything, which is why the
positive case is not optional here.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import binding, h56bridge, hostproof, policy                # noqa: E402

AS_OF = "2026-11-03T04:00:00Z"
BUSINESS = "t"
HOST = "hostA"


def catalogue():
    return policy.load_catalog()


def offer_named(offer_id):
    return next(o for o in catalogue()["offers"] if o["offer_id"] == offer_id)


def order_for(offer_id, amount_minor=None, **overrides):
    offer = offer_named(offer_id)
    order = {
        "order_id": "O-TEST-1",
        "offer_id": offer["offer_id"],
        "amount_minor": offer["amount_minor"] if amount_minor is None else amount_minor,
        "currency": offer["currency"],
        "payee": offer["payee"],
        "amount_source": "CATALOGUE" if amount_minor is None else "CLIENT_SUPPLIED",
    }
    order.update(overrides)
    return order


def run_chain(root, stamp, host_key=HOST, dependencies=True, order=None):
    """One full chain: evidence, request, four cores, binding. Returns everything."""
    names = h56bridge.identifiers(BUSINESS, stamp, host_key=host_key)
    task = h56bridge.task_ref(names["task_id"])
    envelope, raw = hostproof.build(names["environment_id"], task, AS_OF,
                                    values={"dependencies_available": dependencies})
    order = order if order is not None else order_for("S-C01")
    request_id = binding.request_id_for(names["request_id"], order)
    request = h56bridge.request_document(request_id, task, names["environment_id"],
                                        hashlib.sha256(raw).hexdigest(), AS_OF)
    result = h56bridge.evaluate(raw, request, root, names["session"])
    record = binding.make(catalogue(), order, request, raw, result["reference"],
                          names["session"])
    return dict(names=names, task=task, envelope=envelope, raw=raw, order=order,
                request=request, result=result, binding=record)


class PriceTest(unittest.TestCase):
    def test_amount_must_equal_the_catalogue_price(self):
        """The exact case the reviewer measured: a 5000 offer submitted at 1."""
        catalogue_ = catalogue()
        price = offer_named("S-C03")["amount_minor"]
        self.assertEqual(price, 5000)

        under = policy.decide(order_for("S-C03", amount_minor=1), catalogue_)
        self.assertEqual(under["decision"], "BLOCKED")
        self.assertIn("POLICY_AMOUNT_NOT_CATALOGUE_PRICE", under["reason_codes"])
        # The old rules would all have passed: positive integer, under the limit, right
        # currency. That is why this needs its own rule rather than a stricter R1.
        self.assertNotIn("POLICY_AMOUNT_INVALID", under["reason_codes"])
        self.assertNotIn("POLICY_AMOUNT_LIMIT_EXCEEDED", under["reason_codes"])
        self.assertNotIn("POLICY_CURRENCY_MISMATCH", under["reason_codes"])

        over = policy.decide(order_for("S-C01", amount_minor=101), catalogue_)
        self.assertEqual(over["decision"], "BLOCKED")
        self.assertIn("POLICY_AMOUNT_NOT_CATALOGUE_PRICE", over["reason_codes"])

        # Above the limit the breach is reported as a limit breach instead: one bad amount,
        # one code, and the code names the rule the operator can act on first.
        above_limit = policy.decide(order_for("S-C03", amount_minor=price + 1), catalogue_)
        self.assertEqual(above_limit["reason_codes"], ["POLICY_AMOUNT_LIMIT_EXCEEDED"])

    def test_the_catalogue_price_itself_is_allowed(self):
        catalogue_ = catalogue()
        for offer in catalogue_["offers"]:
            verdict = policy.decide(order_for(offer["offer_id"]), catalogue_)
            self.assertEqual(verdict["decision"], "ALLOW", offer["offer_id"])
            self.assertEqual(verdict["reason_codes"], [])
            self.assertIn("R4_CATALOGUE_PRICE", verdict["rules"])

    def test_defaulting_the_amount_marks_it_as_catalogue_priced(self):
        """A defaulted amount cannot disagree with itself; the mark says which claim holds."""
        offer = offer_named("S-C01")
        defaulted = policy_module_build_order(offer["offer_id"], offer)
        self.assertEqual(defaulted["amount_minor"], offer["amount_minor"])
        self.assertEqual(defaulted["amount_source"], "CATALOGUE")
        supplied = policy_module_build_order(offer["offer_id"], offer,
                                             amount_minor=offer["amount_minor"])
        self.assertEqual(supplied["amount_source"], "CLIENT_SUPPLIED")
        # Same number, different provenance, and both are accepted because R4 compares the
        # value rather than trusting the label.
        self.assertEqual(policy.decide(supplied, catalogue())["decision"], "ALLOW")

    def test_a_limit_breach_is_reported_as_the_limit_not_as_the_price(self):
        """One bad amount gets one code, and the first actionable one wins."""
        catalogue_ = catalogue()
        amount = catalogue_["per_order_limit_minor"] + 1
        verdict = policy.decide(order_for("S-C01", amount_minor=amount), catalogue_)
        self.assertEqual(verdict["reason_codes"], ["POLICY_AMOUNT_LIMIT_EXCEEDED"])


def policy_module_build_order(*args, **kwargs):
    """`build_order` lives in `app.main`, which imports the CLI parser; import it lazily."""
    from app.main import build_order
    return build_order(*args, **kwargs)


class BindingTest(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="h56-bind-")
        self.root = Path(self._scratch.name) / "records"
        self.root.mkdir()
        self.run = run_chain(self.root, "b01")

    def tearDown(self):
        self._scratch.cleanup()

    def check_with(self, order=None, request=None, raw=None, record=None):
        return binding.check(record or self.run["binding"], catalogue(),
                             order if order is not None else self.run["order"],
                             request if request is not None else self.run["request"],
                             raw if raw is not None else self.run["raw"])

    def test_a_fresh_consistent_run_has_no_findings(self):
        """The control: without this, "reject everything" would pass every other test."""
        self.assertEqual(self.check_with(), [])

    def test_changing_the_order_amount_is_refused(self):
        edited = dict(self.run["order"], amount_minor=self.run["order"]["amount_minor"] + 1)
        findings = self.check_with(order=edited)
        self.assertIn(binding.ORDER_MISMATCH, findings)
        self.assertIn(binding.PROPOSAL_MISMATCH, findings)

    def test_changing_the_order_id_is_refused(self):
        """The reviewer's second measurement: the id alone used to be free to edit."""
        edited = dict(self.run["order"], order_id="O-SOMETHING-ELSE")
        findings = self.check_with(order=edited)
        self.assertIn(binding.ORDER_MISMATCH, findings)
        # The proposal fields are untouched, so only the order digest broke.
        self.assertNotIn(binding.PROPOSAL_MISMATCH, findings)

    def test_swapping_the_proposal_is_refused(self):
        other = offer_named("S-C02")
        edited = dict(self.run["order"], offer_id=other["offer_id"],
                      amount_minor=other["amount_minor"])
        findings = self.check_with(order=edited)
        self.assertIn(binding.ORDER_MISMATCH, findings)
        self.assertIn(binding.PROPOSAL_MISMATCH, findings)

    def test_reusing_an_old_assessment_for_a_new_order_is_refused(self):
        """A new order with the old request and the old reference must not line up."""
        new_order = order_for("S-C01", amount_minor=self.run["order"]["amount_minor"] + 100)
        findings = self.check_with(order=new_order)
        # Caught at the cheapest link first: the new order's token is not in the old
        # request id, so the pair is refused before any digest is recomputed.
        self.assertIn(binding.ORDER_NOT_IN_REQUEST, findings)
        self.assertIn(binding.ORDER_MISMATCH, findings)

    def test_a_rewritten_request_still_cannot_reuse_the_old_assessment(self):
        """Second layer: an attacker who also rewrites `request_id` gains nothing.

        The order token now matches, so the cheap check passes. What they cannot forge is
        the kernel's own derivation: `assessment_id` is the digest of the whole request, so
        a new request id implies a new assessment id, and the recorded one no longer
        equals it.
        """
        new_order = order_for("S-C01", amount_minor=self.run["order"]["amount_minor"] + 100)
        forged_request = dict(
            self.run["request"],
            request_id=binding.request_id_for(self.run["names"]["request_id"], new_order))
        findings = self.check_with(order=new_order, request=forged_request)
        self.assertNotIn(binding.ORDER_NOT_IN_REQUEST, findings)
        self.assertIn(binding.REQUEST_MISMATCH, findings)
        self.assertIn(binding.ASSESSMENT_FOR_DIFFERENT_REQUEST, findings)

    def test_rewriting_the_binding_without_resealing_is_refused(self):
        forged = dict(self.run["binding"], order_token="0" * binding.ORDER_TOKEN_LENGTH)
        findings = binding.check(forged, catalogue(), self.run["order"],
                                 self.run["request"], self.run["raw"])
        self.assertIn(binding.TAMPERED, findings)

    def test_resealing_a_forged_binding_still_fails_the_order_link(self):
        """Sealing is not the defence; the chain into the kernel is.

        An operator who can edit `binding.json` can reseal it. What they cannot do is make
        the kernel's recorded assessment id equal the digest of a request carrying a
        different order — so the forgery is caught one link further along.
        """
        forged = dict(self.run["binding"], order_sha256="0" * 64,
                      proposal=dict(self.run["binding"]["proposal"], amount_minor=7))
        forged = binding._seal({k: v for k, v in forged.items() if k != "binding_sha256"})
        findings = binding.check(forged, catalogue(), self.run["order"],
                                 self.run["request"], self.run["raw"])
        self.assertNotIn(binding.TAMPERED, findings)
        self.assertIn(binding.ORDER_MISMATCH, findings)
        self.assertIn(binding.PROPOSAL_MISMATCH, findings)

    def test_a_changed_catalogue_is_refused(self):
        drifted = dict(catalogue(), per_order_limit_minor=999999)
        findings = binding.check(self.run["binding"], drifted, self.run["order"],
                                 self.run["request"], self.run["raw"])
        self.assertIn(binding.CATALOGUE_DRIFT, findings)

    def test_the_order_token_is_the_order_digest(self):
        """The link that makes reuse impossible is the token, so pin its definition."""
        token = binding.order_token(self.run["order"])
        self.assertEqual(len(token), binding.ORDER_TOKEN_LENGTH)
        self.assertEqual(token, binding.value_sha256(self.run["order"])[:binding.ORDER_TOKEN_LENGTH])
        self.assertIn(token, self.run["request"]["request_id"])
        self.assertEqual(self.run["binding"]["reference"]["assessment_id"],
                         "ASSESS:" + binding.value_sha256(self.run["request"]))


class SingleVariableTest(unittest.TestCase):
    """A27 as a controlled contrast: one evidence field, both identities pinned."""

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="h56-a27-")
        self.root = Path(self._scratch.name) / "records"
        self.root.mkdir()

    def tearDown(self):
        self._scratch.cleanup()

    def test_the_contrast_differs_in_one_field_and_nothing_structural(self):
        passing = run_chain(self.root, "pos01", host_key=HOST, dependencies=True)
        failing = run_chain(self.root, "neg01", host_key=HOST, dependencies=False)

        # Identities are pinned: the same logical host, not merely "a similar one".
        self.assertEqual(passing["names"]["task_id"], failing["names"]["task_id"])
        self.assertEqual(passing["task"], failing["task"])
        self.assertEqual(passing["envelope"]["environment_id"],
                         failing["envelope"]["environment_id"])
        self.assertEqual(passing["result"]["record"]["environment_id"],
                         failing["result"]["record"]["environment_id"])
        self.assertEqual(passing["result"]["record"]["task_ref"],
                         failing["result"]["record"]["task_ref"])

        # One evidence item moves, and it is the intended one.
        differing = [(a, b) for a, b in zip(passing["envelope"]["items"],
                                            failing["envelope"]["items"]) if a != b]
        self.assertEqual(len(differing), 1)
        left, right = differing[0]
        self.assertEqual(left["field"], "dependencies_available")
        self.assertEqual((left["value"], right["value"]), (True, False))
        self.assertEqual(left["observed_at"], right["observed_at"])
        self.assertEqual(passing["envelope"]["evidence_set_id"],
                         failing["envelope"]["evidence_set_id"])

        # The request differs only where the protocol requires it to.
        moved = {key for key in passing["request"]
                 if passing["request"][key] != failing["request"][key]}
        self.assertEqual(moved, {"request_id", "raw_evidence_sha256"})

        # And the verdicts are the pair, each with its own code.
        self.assertEqual(passing["result"]["record"]["c2_projection"]["decision"], "FEASIBLE")
        negative = failing["result"]["record"]
        self.assertEqual(negative["c2_projection"]["decision"], "INFEASIBLE")
        self.assertIn("ENV_DEPENDENCY_UNAVAILABLE", negative["reason_codes"])
        self.assertIn("DECLARED_POLICY_DENIED", negative["reason_codes"])

        # Two runs, two records: the shared identity does not collapse them.
        self.assertNotEqual(passing["result"]["record"]["assessment_id"],
                            negative["assessment_id"])

    def test_host_key_defaults_to_the_stamp(self):
        """Pinning is opt-in; every earlier call site keeps its old identity."""
        default = h56bridge.identifiers(BUSINESS, "20261103T040000Z")
        pinned = h56bridge.identifiers(BUSINESS, "20261103T040000Z", host_key="other")
        self.assertEqual(default["task_id"], "TASK-t-20261103T040000Z")
        self.assertEqual(default["environment_id"], "ENV-t-20261103T040000Z")
        self.assertEqual(pinned["task_id"], "TASK-t-other")
        self.assertEqual(default["request_id"], pinned["request_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
