"""Sandbox flow tests. No network, no real credential, no kernel.

Every value below that looks like a credential is a literal marked as mock. The tests set
`PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` to those literals for the duration of one test
and restore the previous environment afterwards, so a run of this suite cannot inherit a
real credential from the shell that started it and cannot leave one behind.
"""
import json
import os
import unittest
from pathlib import Path

from app import main, sandbox, settings

ORDER_ID = "MOCK-ORDER-00000001"
CAPTURE_ID = "MOCK-CAPTURE-0000001"

MOCK_TOKEN = "MOCK-TOKEN-NOT-A-CREDENTIAL"
MOCK_SECRET = "MOCK-SECRET-NOT-A-CREDENTIAL"
MOCK_CLIENT = "MOCK-CLIENT-ID-NOT-A-CREDENTIAL"

TOKEN_REPLY = {
    "access_token": MOCK_TOKEN,
    "token_type": "Bearer",
    "expires_in": 31668,
    "app_id": "MOCK-APP-ID-NOT-A-CREDENTIAL",
    "scope": ("https://uri.paypal.com/services/payments/payment "
              "https://uri.paypal.com/services/checkout/orders/read"),
}


def order_document(status="CREATED", value="1.00", currency="USD", with_payer=False):
    document = {
        "id": ORDER_ID,
        "intent": "CAPTURE",
        "status": status,
        "create_time": "2026-11-03T08:00:00Z",
        "purchase_units": [{
            "reference_id": "S-C01",
            "amount": {"currency_code": currency, "value": value},
            "payee": {"email_address": "sb-seller@business.example.com"},
        }],
        "links": [
            {"rel": "self", "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/" + ORDER_ID},
            {"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=" + ORDER_ID},
        ],
    }
    if with_payer:
        document["payer"] = {
            "payer_id": "MOCK-PAYER-ID-NOT-A-CREDENTIAL",
            "email_address": "sb-buyer@personal.example.com",
        }
    return document


def capture_document(value="1.00", currency="USD", status="COMPLETED"):
    return {
        "id": ORDER_ID,
        "status": "COMPLETED",
        "purchase_units": [{
            "payments": {"captures": [{
                "id": CAPTURE_ID,
                "status": status,
                "amount": {"currency_code": currency, "value": value},
                "create_time": "2026-11-03T08:04:11Z",
                "seller_receivable_breakdown": {
                    "paypal_fee": {"currency_code": currency, "value": "0.34"},
                    "net_amount": {"currency_code": currency, "value": "0.66"},
                },
            }]},
        }],
    }


def raw(document):
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


def order(**overrides):
    base = {"offer_id": "S-C01", "description": "Offline qualification item, smallest denomination",
            "amount_minor": 100, "currency": "USD", "payee": "PAYPAL-MERCHANT-SANDBOX-001"}
    base.update(overrides)
    return base


def routes_for(status="APPROVED"):
    path = "/v2/checkout/orders"
    return {
        ("POST", "/v1/oauth2/token"): (200, raw(TOKEN_REPLY)),
        ("POST", path): (201, raw(order_document("CREATED"))),
        ("GET", path + "/" + ORDER_ID): (200, raw(order_document(status, with_payer=status == "APPROVED"))),
        ("POST", path + "/" + ORDER_ID + "/capture"): (201, raw(capture_document())),
    }


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.saved = {name: os.environ.get(name)
                      for name in settings.CREDENTIAL_KEYS + ("PAYPAL_ENVIRONMENT",)}
        os.environ["PAYPAL_CLIENT_ID"] = MOCK_CLIENT
        os.environ["PAYPAL_CLIENT_SECRET"] = MOCK_SECRET
        os.environ.pop("PAYPAL_ENVIRONMENT", None)

    def tearDown(self):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def client(self, routes=None):
        transport = sandbox.MockTransport(routes or routes_for())
        return sandbox.SandboxClient(transport, sandbox.SANDBOX_BASE), transport


class EnvironmentTests(SandboxCase):
    def test_the_only_environment_is_sandbox(self):
        self.assertEqual(sandbox.base_url("sandbox"), sandbox.SANDBOX_BASE)
        for name in ("production", "live", "", "sandbox2", "SANDBOX ", "Sandbox"):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.base_url(name)
            self.assertEqual(caught.exception.code, sandbox.ENVIRONMENT_UNKNOWN)

    def test_a_production_host_is_refused_by_name(self):
        for url in ("https://api-m.paypal.com", "https://api.paypal.com/v2/checkout/orders",
                    "https://www.paypal.com"):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.refuse_production(url)
            self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_the_live_transport_refuses_a_production_base_at_construction(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.LiveTransport("https://api-m.paypal.com")
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_the_environment_variable_cannot_select_production(self):
        os.environ["PAYPAL_ENVIRONMENT"] = "production"
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.base_url()
        self.assertEqual(caught.exception.code, sandbox.ENVIRONMENT_UNKNOWN)

    def test_missing_credentials_are_named_not_defaulted(self):
        os.environ.pop("PAYPAL_CLIENT_ID")
        with self.assertRaises(settings.MissingCredentials) as caught:
            sandbox.credentials()
        self.assertEqual(caught.exception.names, ("PAYPAL_CLIENT_ID",))
        os.environ["PAYPAL_CLIENT_ID"] = MOCK_CLIENT
        os.environ["PAYPAL_CLIENT_SECRET"] = ""
        with self.assertRaises(settings.MissingCredentials) as caught:
            sandbox.credentials()
        self.assertEqual(caught.exception.names, ("PAYPAL_CLIENT_SECRET",))

    def test_credentials_are_read_and_not_written_anywhere(self):
        found = sandbox.credentials()
        self.assertEqual(found, (MOCK_CLIENT, MOCK_SECRET))
        # The function returns the pair and does nothing else: no cache attribute, no file.
        self.assertEqual(os.environ["PAYPAL_CLIENT_SECRET"], MOCK_SECRET)


class AmountTests(SandboxCase):
    def test_minor_units_become_two_decimal_strings(self):
        for minor, text in ((1, "0.01"), (9, "0.09"), (10, "0.10"), (99, "0.99"),
                            (100, "1.00"), (2500, "25.00"), (5000, "50.00"),
                            (12345, "123.45"), (1000000, "10000.00")):
            self.assertEqual(sandbox.amount_value(minor), text)

    def test_amount_refuses_anything_that_is_not_a_positive_int(self):
        for value in (0, -1, -100, 1.0, 0.01, "100", True, False, None, [100]):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.amount_value(value)
            self.assertEqual(caught.exception.code, sandbox.AMOUNT_INVALID)


class BodyTests(SandboxCase):
    def test_the_order_body_mirrors_the_admitted_order(self):
        body = sandbox.create_body(order(), "sb-seller@business.example.com",
                                   "https://example.com/h56/return",
                                   "https://example.com/h56/cancel")
        self.assertEqual(body["intent"], "CAPTURE")
        unit = body["purchase_units"][0]
        self.assertEqual(unit["reference_id"], "S-C01")
        self.assertEqual(unit["amount"], {"currency_code": "USD", "value": "1.00"})
        self.assertEqual(unit["payee"]["email_address"], "sb-seller@business.example.com")
        self.assertEqual(body["application_context"]["user_action"], "PAY_NOW")
        self.assertEqual(body["application_context"]["shipping_preference"], "NO_SHIPPING")

    def test_a_callback_pointing_at_paypal_production_is_refused(self):
        for url in ("https://api-m.paypal.com/h56/return", "http://example.com/h56/return"):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.create_body(order(), "sb-seller@business.example.com", url,
                                    "https://example.com/h56/cancel")
            self.assertEqual(caught.exception.code,
                             sandbox.SANDBOX_HOST_REFUSED if url.startswith("https")
                             else sandbox.CALLBACK_INVALID)

    def test_the_body_refuses_a_bad_currency_or_payee(self):
        with self.assertRaises(sandbox.SandboxError):
            sandbox.create_body(order(currency="US"), "sb-seller@business.example.com",
                                "https://example.com/a", "https://example.com/b")
        with self.assertRaises(sandbox.SandboxError):
            sandbox.create_body(order(), "not-an-address",
                                "https://example.com/a", "https://example.com/b")


class CommitKeyTests(SandboxCase):
    def test_the_key_is_derived_from_the_seed_and_stable(self):
        seed = "a" * 64
        self.assertEqual(sandbox.commit_key(seed), sandbox.commit_key(seed))
        self.assertEqual(sandbox.commit_key(seed), "h56-capture-" + "a" * 32)
        self.assertNotEqual(sandbox.commit_key(seed), sandbox.commit_key("b" * 64))

    def test_the_key_refuses_a_seed_that_is_not_a_digest(self):
        for seed in ("", "abc", "z" * 64, "A" * 63, None, 12345):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.commit_key(seed)
            self.assertEqual(caught.exception.code, sandbox.KEY_SEED_INVALID)


class ApprovalTests(SandboxCase):
    def test_a_governance_verdict_never_stands_in_for_the_buyers_approval(self):
        """The whole distinction, in one test: FEASIBLE is not consent."""
        created = {"status": sandbox.CREATED}
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.capture_preconditions(created, decision="FEASIBLE")
        self.assertEqual(caught.exception.code, sandbox.PAYER_NOT_APPROVED)
        self.assertIn("h56=FEASIBLE", caught.exception.detail)

    def test_approval_permits_capture_even_when_governance_said_infeasible(self):
        """The other direction: the two facts are independent, not merely ordered."""
        self.assertEqual(sandbox.capture_preconditions({"status": sandbox.APPROVED},
                                                       decision="INFEASIBLE"),
                         sandbox.CAPTURE_READY)

    def test_a_completed_order_is_captured_once_only(self):
        self.assertEqual(sandbox.capture_preconditions({"status": sandbox.COMPLETED}),
                         sandbox.ALREADY_CAPTURED)

    def test_an_unknown_state_is_refused_rather_than_guessed(self):
        for status in (None, "", "PAYER_ACTION_REQUIRED", "VOIDED", "SAVED"):
            with self.assertRaises(sandbox.SandboxError) as caught:
                sandbox.capture_preconditions({"status": status})
            self.assertEqual(caught.exception.code, sandbox.PAYER_NOT_APPROVED)


class VerifyCaptureTests(SandboxCase):
    def test_a_capture_matching_the_catalogue_passes(self):
        captured = sandbox.parse_capture(raw(capture_document()))
        self.assertTrue(sandbox.verify_capture(captured, 100, "USD"))
        self.assertEqual(captured["fee_value"], "0.34")
        self.assertEqual(captured["net_value"], "0.66")

    def test_a_capture_of_a_different_amount_is_refused(self):
        captured = sandbox.parse_capture(raw(capture_document(value="0.99")))
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.verify_capture(captured, 100, "USD")
        self.assertEqual(caught.exception.code, sandbox.CAPTURE_AMOUNT_MISMATCH)

    def test_a_capture_in_another_currency_is_refused(self):
        captured = sandbox.parse_capture(raw(capture_document(currency="EUR")))
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.verify_capture(captured, 100, "USD")
        self.assertEqual(caught.exception.code, sandbox.CAPTURE_CURRENCY_MISMATCH)

    def test_a_capture_that_did_not_complete_is_refused(self):
        captured = sandbox.parse_capture(raw(capture_document(status="DECLINED")))
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.verify_capture(captured, 100, "USD")
        self.assertEqual(caught.exception.code, sandbox.ORDER_STATE_UNEXPECTED)

    def test_a_response_without_a_capture_is_not_read_as_success(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.parse_capture(raw({"id": ORDER_ID, "status": "COMPLETED",
                                       "purchase_units": [{"payments": {}}]}))
        self.assertEqual(caught.exception.code, sandbox.CAPTURE_MISSING)


class RoundTripTests(SandboxCase):
    def test_the_four_calls_happen_once_each_and_only_against_the_sandbox(self):
        client, transport = self.client()
        created = client.create_order(order(), "sb-seller@business.example.com",
                                      "https://example.com/h56/return",
                                      "https://example.com/h56/cancel")
        self.assertEqual(created["status"], sandbox.CREATED)
        self.assertIn("sandbox.paypal.com", created["approve_url"])
        self.assertIsNone(created["payer_ref"])

        seen = client.read_order(ORDER_ID)
        self.assertEqual(seen["status"], sandbox.APPROVED)
        self.assertIsNotNone(seen["payer_ref"])
        self.assertEqual(len(seen["payer_ref"]), 16)

        self.assertEqual(sandbox.capture_preconditions(seen, "FEASIBLE"), sandbox.CAPTURE_READY)
        captured = client.capture_order(ORDER_ID, "c" * 64, 100, "USD")
        self.assertEqual(captured["capture_id"], CAPTURE_ID)
        self.assertEqual(captured["value"], "1.00")

        self.assertEqual(len(transport.calls), 4)
        for method, url in transport.calls:
            self.assertIn("sandbox", url, "%s %s is not a sandbox call" % (method, url))
        self.assertEqual([m for m, _ in transport.calls], ["POST", "POST", "GET", "POST"])

    def test_the_capture_request_carries_the_derived_key(self):
        client, transport = self.client()
        client.capture_order(ORDER_ID, "d" * 64, 100, "USD")
        self.assertEqual(transport.calls[-1][1],
                         sandbox.SANDBOX_BASE + "/v2/checkout/orders/" + ORDER_ID + "/capture")

    def test_a_refused_create_does_not_continue(self):
        routes = routes_for()
        routes[("POST", "/v2/checkout/orders")] = (422, raw({"name": "UNPROCESSABLE_ENTITY"}))
        client, transport = self.client(routes)
        with self.assertRaises(sandbox.SandboxError) as caught:
            client.create_order(order(), "sb-seller@business.example.com",
                                "https://example.com/a", "https://example.com/b")
        self.assertEqual(caught.exception.code, sandbox.RESPONSE_REFUSED)
        self.assertEqual(len(transport.calls), 2)  # token, then the refused create

    def test_an_order_that_comes_back_in_the_wrong_state_is_not_accepted(self):
        routes = routes_for()
        routes[("POST", "/v2/checkout/orders")] = (201, raw(order_document("COMPLETED")))
        client, _ = self.client(routes)
        with self.assertRaises(sandbox.SandboxError) as caught:
            client.create_order(order(), "sb-seller@business.example.com",
                                "https://example.com/a", "https://example.com/b")
        self.assertEqual(caught.exception.code, sandbox.ORDER_STATE_UNEXPECTED)

    def test_an_unparsable_response_is_not_a_pass(self):
        routes = routes_for()
        routes[("POST", "/v2/checkout/orders")] = (201, b"<html>not json</html>")
        client, _ = self.client(routes)
        with self.assertRaises(sandbox.SandboxError) as caught:
            client.create_order(order(), "sb-seller@business.example.com",
                                "https://example.com/a", "https://example.com/b")
        self.assertEqual(caught.exception.code, sandbox.RESPONSE_UNREADABLE)


class RedactionTests(SandboxCase):
    def test_a_token_and_an_address_do_not_survive_redaction(self):
        document = {
            "access_token": MOCK_TOKEN,
            "payer": {"email_address": "sb-buyer@personal.example.com",
                      "payer_id": "MOCK-PAYER-ID-NOT-A-CREDENTIAL"},
            "app_id": "MOCK-APP-ID-NOT-A-CREDENTIAL",
            "note": "keep me",
        }
        ledger = {}
        cleaned = sandbox.redact(document, ledger)
        text = sandbox.dumps(cleaned)
        self.assertNotIn(MOCK_TOKEN, text)
        self.assertNotIn("sb-buyer@personal.example.com", text)
        self.assertNotIn("MOCK-PAYER-ID-NOT-A-CREDENTIAL", text)
        self.assertNotIn("MOCK-APP-ID-NOT-A-CREDENTIAL", text)
        self.assertIn("keep me", text)
        self.assertIn("<redacted %d chars>" % len(MOCK_TOKEN), text)
        self.assertEqual(ledger.get("access_token"), 1)

    def test_a_bearer_header_is_masked(self):
        cleaned = sandbox.redact({"Authorization": "Bearer %s" % MOCK_TOKEN})
        self.assertEqual(cleaned["Authorization"], "Bearer <redacted>")

    def test_the_fingerprint_is_a_digest_and_a_length(self):
        mark = sandbox.fingerprint(b"{}")
        self.assertEqual(mark["bytes"], 2)
        self.assertEqual(len(mark["sha256"]), 64)
        self.assertNotIn("{}", sandbox.dumps(mark))


class RealmTests(SandboxCase):
    def test_the_realm_reports_scope_and_a_reference_never_the_app_id(self):
        client, _ = self.client()
        realm = client.realm()
        self.assertEqual(realm["expires_in"], 31668)
        self.assertEqual(len(realm["app_id_ref"]), 16)
        self.assertNotIn("MOCK-APP-ID", sandbox.dumps(realm))
        self.assertIn("https://uri.paypal.com/services/payments/payment", realm["scopes"])


class TransportEndpointTests(SandboxCase):
    """The endpoint rule is identity, not containment: measured by the auditor, a host
    that merely contained the word "sandbox" was accepted, and so was cleartext http."""

    def test_the_pinned_endpoint_is_accepted(self):
        self.assertEqual(sandbox.require_api_endpoint(sandbox.SANDBOX_BASE + sandbox.TOKEN_PATH),
                         sandbox.SANDBOX_BASE + sandbox.TOKEN_PATH)

    def test_a_lookalike_host_containing_sandbox_is_refused(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.require_api_endpoint("https://sandbox.attacker.invalid/v1/oauth2/token")
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_cleartext_http_is_refused_even_on_the_right_host(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.require_api_endpoint("http://api-m.sandbox.paypal.com/v1/oauth2/token")
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_the_production_host_is_refused_here_too(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.require_api_endpoint("https://api-m.paypal.com/v1/oauth2/token")
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_the_live_transport_refuses_a_lookalike_base_at_construction(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.LiveTransport("https://sandbox.attacker.invalid")
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)

    def test_the_mock_enforces_the_same_endpoint_rule_as_the_wire(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.MockTransport().post("https://api-m.paypal.com/v1/oauth2/token",
                                         {}, {})
        self.assertEqual(caught.exception.code, sandbox.SANDBOX_HOST_REFUSED)


class WireFormatTests(SandboxCase):
    """What actually goes on the wire, caught by sitting where LiveTransport sits.

    The auditor's interception found a JSON token body travelling under a form header;
    a mock that only replays responses never sees that shape, so the bytes are recorded
    and asserted here.
    """

    SPY_ROUTES = {("POST", "/v1/oauth2/token"): (200, raw(TOKEN_REPLY)),
                  ("POST", "/v2/checkout/orders"): (201, raw(order_document("CREATED")))}

    def test_the_token_is_sent_as_a_form_and_the_header_is_not_overwritten(self):
        transport = sandbox.SpyTransport(self.SPY_ROUTES)
        client = sandbox.SandboxClient(transport, sandbox.SANDBOX_BASE)
        client.token()
        method, url, payload, headers = transport.sent[0]
        self.assertEqual(payload, b"grant_type=client_credentials")
        self.assertEqual(headers.get("Content-Type"),
                         sandbox.FORM_TYPE)
        self.assertTrue(headers.get("Authorization", "").startswith("Basic "))

    def test_an_order_is_sent_as_json_with_its_request_id(self):
        transport = sandbox.SpyTransport(self.SPY_ROUTES)
        client = sandbox.SandboxClient(transport, sandbox.SANDBOX_BASE)
        client.create_order(order(), "sb-seller@business.example.com",
                            "https://example.com/r", "https://example.com/c",
                            request_id="h56-create-" + "a" * 32)
        method, url, payload, headers = transport.sent[-1]
        self.assertEqual(headers.get("Content-Type"), sandbox.JSON_TYPE)
        self.assertEqual(headers.get("PayPal-Request-Id"), "h56-create-" + "a" * 32)
        body = json.loads(payload.decode("utf-8"))
        self.assertEqual(body["purchase_units"][0]["amount"]["value"], "1.00")

    def test_an_unspeakable_content_type_is_refused_before_any_byte_is_built(self):
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.encode_request({}, {"Content-Type": "application/xml"})
        self.assertEqual(caught.exception.code, sandbox.TRANSPORT_REFUSED)


class OrderVerificationTests(SandboxCase):
    """Identity, money and payee, checked against what PayPal holds -- before capture."""

    def test_parse_order_names_the_payee_as_a_reference(self):
        view = sandbox.parse_order(raw(order_document()))
        self.assertEqual(view["payee_ref"],
                         sandbox.payee_ref("sb-seller@business.example.com"))

    def test_a_matching_order_verifies(self):
        view = sandbox.parse_order(raw(order_document()))
        self.assertTrue(sandbox.verify_order(view, ORDER_ID, order(),
                                             sandbox.payee_ref("sb-seller@business.example.com")))

    def _refused(self, document, order_id=ORDER_ID, payee=None):
        view = sandbox.parse_order(raw(document))
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.verify_order(view, order_id, order(),
                                 payee or sandbox.payee_ref("sb-seller@business.example.com"))
        self.assertEqual(caught.exception.code, sandbox.ORDER_MISMATCH)

    def test_a_different_order_id_is_refused(self):
        self._refused(order_document(), order_id="O-OTHER")

    def test_a_different_amount_is_refused_before_any_capture(self):
        self._refused(order_document(value="2.00"))

    def test_a_different_currency_is_refused_before_any_capture(self):
        self._refused(order_document(currency="EUR"))

    def test_an_unnamed_payee_is_refused_rather_than_assumed(self):
        document = order_document()
        del document["purchase_units"][0]["payee"]
        self._refused(document)

    def test_a_different_payee_is_refused(self):
        self._refused(order_document(), payee=sandbox.payee_ref("sb-other@business.example.com"))


class PendingCaptureTests(SandboxCase):
    """A pending capture is an accepted request, not money that moved."""

    def test_a_pending_capture_is_reported_as_pending_not_successful(self):
        captured = sandbox.parse_capture(raw(capture_document(status="PENDING")))
        self.assertEqual(sandbox.verify_capture(captured, 100, "USD"), "PENDING")

    def test_a_completed_capture_is_reported_as_completed(self):
        captured = sandbox.parse_capture(raw(capture_document()))
        self.assertEqual(sandbox.verify_capture(captured, 100, "USD"), "COMPLETED")

    def test_a_declined_capture_is_still_refused(self):
        captured = sandbox.parse_capture(raw(capture_document(status="DECLINED")))
        with self.assertRaises(sandbox.SandboxError) as caught:
            sandbox.verify_capture(captured, 100, "USD")
        self.assertEqual(caught.exception.code, sandbox.ORDER_STATE_UNEXPECTED)


class CreateKeyTests(SandboxCase):
    """The create has its own derived key: same operation, same key, whatever restarted."""

    def test_the_create_key_is_stable_and_prefixed(self):
        seed = sandbox.create_seed(order(), "sb-seller@business.example.com")
        self.assertEqual(sandbox.create_key(seed), sandbox.create_key(seed))
        self.assertTrue(sandbox.create_key(seed).startswith("h56-create-"))

    def test_different_operations_have_different_keys(self):
        seed = sandbox.create_seed(order(), "sb-seller@business.example.com")
        variants = {sandbox.create_key(seed),
                    sandbox.create_key(sandbox.create_seed(
                        order(amount_minor=2500), "sb-seller@business.example.com")),
                    sandbox.create_key(sandbox.create_seed(
                        order(), "sb-other@business.example.com")),
                    sandbox.create_key(sandbox.create_seed(
                        order(offer_id="S-C02"), "sb-seller@business.example.com"))}
        self.assertEqual(len(variants), 4)

    def test_the_capture_key_is_unchanged(self):
        self.assertEqual(sandbox.commit_key("c" * 64).startswith("h56-capture-"), True)

    def test_an_unknown_operation_or_bad_seed_is_refused(self):
        with self.assertRaises(sandbox.SandboxError):
            sandbox.operation_key("refund", "c" * 64)
        with self.assertRaises(sandbox.SandboxError):
            sandbox.create_key("not-a-digest")


class IntentStateTests(SandboxCase):
    """The persisted state before a send: what a crash leaves behind has a name."""

    def setUp(self):
        SandboxCase.setUp(self)
        import tempfile
        self.root = Path(tempfile.mkdtemp(prefix="h56-intent-"))
        self.directory = self.root / "20261103T030000Z_shop"
        (self.directory / "paypal").mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)
        SandboxCase.tearDown(self)

    def test_a_directory_without_an_intent_is_not_an_error(self):
        empty = self.root / "20261103T030100Z_shop"
        empty.mkdir()
        self.assertIsNone(main._read_intent(empty))

    def test_an_unparsable_intent_is_an_unnamed_state(self):
        (self.directory / "paypal" / "00_intent.json").write_bytes(b"{not json")
        with self.assertRaises(sandbox.SandboxError) as caught:
            main._read_intent(self.directory)
        self.assertEqual(caught.exception.code, sandbox.RUN_STATE_UNKNOWN)

    def test_an_intent_without_a_key_is_an_unnamed_state(self):
        (self.directory / "paypal" / "00_intent.json").write_bytes(b'{"state":"PENDING_SEND"}')
        with self.assertRaises(sandbox.SandboxError) as caught:
            main._read_intent(self.directory)
        self.assertEqual(caught.exception.code, sandbox.RUN_STATE_UNKNOWN)

    def test_a_written_intent_round_trips(self):
        main._write_intent(self.directory, {"create_key": "h56-create-" + "a" * 32,
                                            "state": "PENDING_SEND"})
        intent = main._read_intent(self.directory)
        self.assertEqual(intent["create_key"], "h56-create-" + "a" * 32)


class H56GateTests(unittest.TestCase):
    """The execution gate, against a real evaluation: real chain, real kernel record.

    The auditor's measurement was that create and capture reached the wire with a real
    INFEASIBLE record in the same directory and the binding consulted zero times. These
    tests run the actual `evaluate` into temporary roots and then put the gate in front
    of it, so the refusals are the gate's own, not a stand-in's.
    """

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        cls.saved = (settings.RUNS_ROOT, settings.RECORDS_ROOT)
        cls.root = Path(tempfile.mkdtemp(prefix="h56-gate-"))
        settings.RUNS_ROOT = cls.root / "runs"
        settings.RECORDS_ROOT = cls.root / "records"

    @classmethod
    def tearDownClass(cls):
        settings.RUNS_ROOT, settings.RECORDS_ROOT = cls.saved
        import shutil
        shutil.rmtree(cls.root, ignore_errors=True)

    def evaluate(self, stamp, dependencies="true", as_of=None):
        from app import main as app_main
        arguments = ["evaluate", "--offer-id", "S-C01", "--business", "shop",
                     "--stamp", stamp, "--host-key", "hostA",
                     "--dependencies", dependencies]
        if as_of:
            arguments += ["--as-of", as_of]
        code = app_main.main(arguments)
        assert code == 0, "evaluate failed with %d" % code
        return settings.RUNS_ROOT / ("%s_shop" % stamp)

    def gate(self, stamp, offer="S-C01", directory=None):
        from app import main as app_main, policy
        catalogue_ = policy.load_catalog()
        offer_doc = next(o for o in catalogue_["offers"] if o["offer_id"] == offer)
        chain_order = {"offer_id": offer_doc["offer_id"],
                       "description": offer_doc["description"],
                       "amount_minor": offer_doc["amount_minor"],
                       "currency": offer_doc["currency"], "payee": offer_doc["payee"]}
        return app_main._h56_gate(stamp, "shop", chain_order, catalogue_,
                                  directory=directory, records_root=settings.RECORDS_ROOT)

    def test_a_feasible_run_passes_the_gate_and_names_its_assessment(self):
        directory = self.evaluate("20261103T030001Z")
        gate = self.gate("20261103T030001Z")
        self.assertEqual(gate["decision"], "FEASIBLE")
        self.assertTrue(str(gate["assessment_id"]).startswith("ASSESS:"))
        self.assertLess(gate["evaluation_age_seconds"], sandbox.MAX_EVALUATION_AGE_SECONDS)
        self.assertEqual(gate["directory"], directory)

    def test_an_infeasible_run_is_refused_by_the_gate(self):
        self.evaluate("20261103T030002Z", dependencies="false")
        with self.assertRaises(sandbox.SandboxError) as caught:
            self.gate("20261103T030002Z")
        self.assertEqual(caught.exception.code, sandbox.H56_DECISION_NOT_FEASIBLE)

    def test_an_edited_verdict_is_refused_by_the_binding(self):
        directory = self.evaluate("20261103T030003Z")
        result = json.loads((directory / "result.json").read_bytes().decode("utf-8"))
        result["decision"] = "INFEASIBLE"
        (directory / "result.json").write_bytes(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        with self.assertRaises(sandbox.SandboxError) as caught:
            self.gate("20261103T030003Z")
        self.assertEqual(caught.exception.code, sandbox.H56_BINDING_INVALID)

    def test_executing_a_different_offer_is_refused(self):
        self.evaluate("20261103T030004Z")
        with self.assertRaises(sandbox.SandboxError) as caught:
            self.gate("20261103T030004Z", offer="S-C03")
        self.assertEqual(caught.exception.code, sandbox.H56_ORDER_MISMATCH)

    def test_a_missing_evaluation_file_is_a_missing_record(self):
        directory = self.evaluate("20261103T030005Z")
        (directory / "binding.json").unlink()
        with self.assertRaises(sandbox.SandboxError) as caught:
            self.gate("20261103T030005Z")
        self.assertEqual(caught.exception.code, sandbox.H56_RECORD_MISSING)

    def test_an_evaluation_from_yesterday_is_stale(self):
        self.evaluate("20261103T030006Z", as_of="2020-01-01T00:00:00Z")
        with self.assertRaises(sandbox.SandboxError) as caught:
            self.gate("20261103T030006Z")
        self.assertEqual(caught.exception.code, sandbox.H56_EVALUATION_STALE)


if __name__ == "__main__":
    unittest.main()
