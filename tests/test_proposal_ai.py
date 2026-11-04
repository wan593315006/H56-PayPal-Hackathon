"""The AI proposal node: structural refusals, mock-driven end-to-end runs, key quietness.

Every network-facing claim is tested against the MockProvider or against refusals that
fire before any socket call. The offline network guard installed by run_offline_tests.py
is the backstop: if any code path here opened a socket, the whole suite would fail, not
just one case.
"""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path

from unittest import mock

from app import main as app_main
from app import proposal_ai, settings


def _valid(text_overrides=None):
    proposal = json.loads(proposal_ai.MOCK_RESPONSE_DEFAULT)
    proposal.update(text_overrides or {})
    return json.dumps(proposal, sort_keys=True)


class ParseTest(unittest.TestCase):
    def test_default_mock_response_parses(self):
        proposal = proposal_ai.parse_proposal(proposal_ai.MOCK_RESPONSE_DEFAULT)
        self.assertEqual(sorted(proposal), sorted(proposal_ai.PROPOSAL_KEYS))
        self.assertEqual(proposal["offer_id"], "S-C02")
        self.assertEqual(proposal["amount_minor"], 2500)

    def test_prose_around_the_object_is_tolerated(self):
        text = "Here is the order you asked for:\n```json\n%s\n```\nLet me know." % _valid()
        proposal = proposal_ai.parse_proposal(text)
        self.assertEqual(proposal["order_id"], "O-AI-DEMO-1")

    def test_braces_inside_strings_do_not_confuse_the_scanner(self):
        # Scanner level: braces and quotes inside a string literal are opaque. (The
        # field-level checks refuse such an order_id later; this test pins the scanner.)
        text = 'prefix {"offer_id": "S-{weird}-\\"x", "n": 1} suffix'
        spans, array_seen = proposal_ai._scan_top_level(text)
        self.assertFalse(array_seen)
        self.assertEqual(len(spans), 1)
        self.assertEqual(text[spans[0][0]:spans[0][1]], '{"offer_id": "S-{weird}-\\"x", "n": 1}')

    def test_second_object_is_a_refusal(self):
        text = "%s\n%s" % (_valid(), _valid({"order_id": "O-SECOND"}))
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_MULTIPLE_OBJECTS")

    def test_array_wrapped_object_is_a_refusal(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal("[%s]" % _valid())
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_ARRAY_WRAPPED")

    def test_bare_array_is_array_refusal(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal('[1, 2, 3]')
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_ARRAY_WRAPPED")

    def test_bracket_in_trailing_prose_is_refused(self):
        # Fail-closed: the prompt forbids extra content, so prose carrying structure
        # characters is refused rather than guessed around.
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal("%s\nsee reference [1] for details" % _valid())
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_ARRAY_WRAPPED")

    def test_duplicate_key_does_not_silently_win(self):
        text = ('{"offer_id": "S-C01", "offer_id": "S-C02", "order_id": "O-1",'
                ' "amount_minor": 100, "currency": "USD", "payee": "PAYPAL-MERCHANT-SANDBOX-001"}')
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_DUPLICATE_KEY")
        self.assertIn("offer_id", str(caught.exception))

    def test_newline_in_order_id_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"order_id": "O-AI\nDEMO-1"}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_FIELD_CHARS")

    def test_tab_in_payee_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"payee": "PAYPAL\tMERCHANT"}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_FIELD_CHARS")

    def test_order_id_shape_is_pinned(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"order_id": "O AI DEMO"}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_ORDER_ID_INVALID")

    def test_lone_surrogate_in_a_field_is_refused(self):
        # json.loads accepts the \ud800 escape; no UTF-8 encoding of it exists, so the
        # refusal must happen here and not at evidence-write time.
        text = _valid({"order_id": "O-\ud800-X"})
        self.assertIn("\\ud800", text)  # the transport shape really carries the escape
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_FIELD_ENCODING")

    def test_deeply_nested_json_is_refused_by_name(self):
        text = '{"a":' * 20000 + "1" + "}" * 20000
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_JSON_TOO_DEEP")

    def test_unreasonably_huge_amount_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"amount_minor": 10 ** 400}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_AMOUNT_VALUE")

    def test_check_encodable_refuses_surrogate_prose(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.check_encodable("fine prose \ud800 tail")
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_EVIDENCE_ENCODING")
        self.assertEqual(proposal_ai.check_encodable("fine prose"), "fine prose")

    def test_no_object_at_all(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal("I cannot help with that.")
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_NO_JSON_OBJECT")

    def test_unbalanced_object(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal('{"offer_id": "S-C01"')
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_UNBALANCED_OBJECT")

    def test_malformed_json_inside_braces(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal('{"offer_id": S-C01}')
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_MALFORMED_JSON")

    def test_extra_key_is_a_refusal(self):
        text = _valid({"verdict": "FEASIBLE"})
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_KEY_SET_MISMATCH")
        self.assertIn("verdict", str(caught.exception))

    def test_missing_key_is_a_refusal(self):
        text = json.dumps({key: value for key, value in json.loads(_valid()).items()
                           if key != "payee"})
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_KEY_SET_MISMATCH")
        self.assertIn("payee", str(caught.exception))

    def test_float_amount_is_refused_by_the_parser_itself(self):
        text = _valid({"amount_minor": 25.0})
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(text)
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_FLOAT_AMOUNT")

    def test_bool_amount_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"amount_minor": True}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_AMOUNT_TYPE")

    def test_non_positive_amount_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"amount_minor": 0}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_AMOUNT_VALUE")

    def test_empty_field_is_refused(self):
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal(_valid({"payee": ""}))
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_FIELD_TYPE")


class RemoteProviderRefusalTest(unittest.TestCase):
    """Refusals that must fire before any socket is opened."""

    def test_insecure_endpoint_refused_without_touching_the_environment(self):
        provider = proposal_ai.RemoteProvider("http://api.example.com", "m", "NO_SUCH_KEY")
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            provider.complete("prompt")
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_INSECURE_ENDPOINT")

    def test_missing_key_refused_by_name_only(self):
        provider = proposal_ai.RemoteProvider("https://api.example.com", "m",
                                              "H56PAY_TEST_NO_SUCH_KEY")
        saved = os.environ.pop("H56PAY_TEST_NO_SUCH_KEY", None)
        try:
            with self.assertRaises(proposal_ai.ProposalAIError) as caught:
                provider.complete("prompt")
        finally:
            if saved is not None:
                os.environ["H56PAY_TEST_NO_SUCH_KEY"] = saved
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_CREDENTIALS_MISSING")
        self.assertIn("H56PAY_TEST_NO_SUCH_KEY", str(caught.exception))

    def test_meta_never_carries_a_key_value(self):
        provider = proposal_ai.RemoteProvider("https://api.example.com", "m", "KEY_ENV")
        meta = provider.meta()
        self.assertEqual(meta["key_env"], "KEY_ENV")
        self.assertNotIn("key", "".join(str(value) for value in meta.values()).lower()
                         .replace("key_env", ""))

    def test_redirect_is_refused_by_name(self):
        # Zero-network check of the redirect refusal: the handler is invoked directly,
        # the way urllib's default machinery would call it on a 3xx.
        handler = proposal_ai._NoRedirect()
        request = urllib.request.Request("https://api.example.com/chat/completions")
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            handler.redirect_request(request, None, 302, "Found",
                                     {"Location": "http://elsewhere.example.com/x"},
                                     "http://elsewhere.example.com/x")
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_REDIRECT_REFUSED")

    def test_default_opener_carries_the_no_redirect_handler(self):
        opener = urllib.request.build_opener(proposal_ai._NoRedirect)
        self.assertTrue(any(isinstance(h, proposal_ai._NoRedirect) for h in opener.handlers))

    def test_request_body_states_an_output_cap_and_sends_the_key(self):
        provider = proposal_ai.RemoteProvider("https://api.example.com", "model-x", "KEY_ENV",
                                              max_output_tokens=256)
        request = provider._request("prompt text", "secret-value")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["max_tokens"], 256)
        self.assertEqual(body["model"], "model-x")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-value")
        self.assertEqual(request.full_url, "https://api.example.com/chat/completions")
        # The request object is built without touching the environment or the network.

    def test_response_body_cap_constant_is_bounded(self):
        self.assertLessEqual(proposal_ai.MAX_RESPONSE_BYTES, 4 << 20)

    def test_reserved_key_env_is_refused(self):
        # The .env-managed PayPal keys must not be routable through the model transport.
        for reserved in settings.ALLOWED_ENV_KEYS:
            with self.assertRaises(proposal_ai.ProposalAIError) as caught:
                proposal_ai.RemoteProvider("https://api.example.com", "m", reserved)
            self.assertEqual(caught.exception.code, "PROPOSAL_AI_KEY_ENV_RESERVED")

    def test_reserved_key_env_is_refused_case_insensitively(self):
        # F1: Windows normalises variable names on lookup -- `paypal_client_secret`
        # reads the very variable .env manages as PAYPAL_CLIENT_SECRET. The reserved
        # rule must compare canonical forms, not spellings.
        for variant in ("paypal_client_secret", "PayPal_Client_Secret",
                        "PAYPAL_client_ID", "paypal_ENVIRONMENT"):
            with self.assertRaises(proposal_ai.ProposalAIError) as caught:
                proposal_ai.RemoteProvider("https://api.example.com", "m", variant)
            self.assertEqual(caught.exception.code, "PROPOSAL_AI_KEY_ENV_RESERVED",
                             variant)
        self.assertTrue(settings.is_reserved_env_key("PayPal_Client_Secret"))
        self.assertFalse(settings.is_reserved_env_key("H56PAY_MODEL_KEY"))


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    def read(self, limit=-1):
        return self._payload if limit < 0 else self._payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    def __init__(self, result):
        self._result = result
        self.opened = None

    def open(self, request, timeout=None):
        self.opened = request
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class RemoteFailureFamilyTest(unittest.TestCase):
    """The live-call refusal family, exercised with zero sockets via a fake opener."""

    KEY_ENV = "H56PAY_TEST_REMOTE_KEY"

    def setUp(self):
        self._saved = os.environ.get(self.KEY_ENV)
        os.environ[self.KEY_ENV] = "secret-value"
        self.provider = proposal_ai.RemoteProvider("https://api.example.com", "m", self.KEY_ENV)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(self.KEY_ENV, None)
        else:
            os.environ[self.KEY_ENV] = self._saved

    def _run(self, result):
        opener = _FakeOpener(result)
        with mock.patch("urllib.request.build_opener", return_value=opener) as factory:
            outcome = {}
            try:
                outcome["content"] = self.provider.complete(proposal_ai.MOCK_RESPONSE_DEFAULT)
                outcome["error"] = None
            except proposal_ai.ProposalAIError as error:
                outcome["error"] = error
        # The wiring claim, asserted where the patch already reaches: complete() must
        # build its opener with the no-redirect handler, not merely define one.
        factory.assert_called_once()
        self.assertIs(factory.call_args.args[0], proposal_ai._NoRedirect)
        return opener, outcome

    def test_http_error_reports_status_only_and_never_the_key(self):
        import urllib.error
        opener, outcome = self._run(urllib.error.HTTPError(
            "https://api.example.com/chat/completions", 401, "Unauthorized", {}, None))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_HTTP_STATUS")
        self.assertIn("401", str(outcome["error"]))
        self.assertNotIn("secret-value", str(outcome["error"]))
        self.assertIsNotNone(opener.opened)

    def test_unparseable_body_is_refused(self):
        _opener, outcome = self._run(_FakeResponse(200, b"this is not json"))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_UNPARSEABLE")

    def test_oversized_body_is_refused(self):
        _opener, outcome = self._run(_FakeResponse(200, b"x" * (proposal_ai.MAX_RESPONSE_BYTES + 1)))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_TOO_LARGE")

    def test_empty_choice_is_refused(self):
        body = json.dumps({"choices": [{"message": {"content": "  "}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_EMPTY_CHOICE")

    def test_happy_path_returns_content_and_sends_bearer_once(self):
        body = json.dumps({"choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        opener, outcome = self._run(_FakeResponse(200, body))
        self.assertIsNone(outcome["error"])
        self.assertEqual(outcome["content"], proposal_ai.MOCK_RESPONSE_DEFAULT)
        self.assertEqual(opener.opened.get_header("Authorization"), "Bearer secret-value")

    def test_happy_path_records_the_server_receipt(self):
        # R2: what the server said about the call -- id, model echo, usage, status and
        # a digest of the exact bytes -- must survive the call, not just the content.
        body = json.dumps({
            "id": "AUDIT_RESPONSE_ID", "model": "AUDIT_RETURNED_MODEL",
            "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17},
            "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}],
        }).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertIsNone(outcome["error"])
        receipt = self.provider.last_receipt
        self.assertEqual(receipt["response_id"], "AUDIT_RESPONSE_ID")
        self.assertEqual(receipt["returned_model"], "AUDIT_RETURNED_MODEL")
        self.assertEqual(receipt["usage"],
                         {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17})
        self.assertEqual(receipt["http_status"], 200)
        self.assertEqual(receipt["response_bytes"], len(body))
        self.assertEqual(receipt["response_sha256"], hashlib.sha256(body).hexdigest())
        # meta separates what was configured from what came back; the receipt rides
        # along into provenance. Still no key value anywhere.
        meta = self.provider.meta()
        self.assertEqual(meta["configured_model"], "m")
        self.assertEqual(meta["returned_model"], "AUDIT_RETURNED_MODEL")
        self.assertEqual(meta["server_receipt"], receipt)
        self.assertNotIn("secret-value", json.dumps(meta))

    def test_receipt_fields_the_server_omits_are_marked_missing(self):
        body = json.dumps({"choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertIsNone(outcome["error"])
        receipt = self.provider.last_receipt
        self.assertEqual(receipt["response_id"], "missing")
        self.assertEqual(receipt["returned_model"], "missing")
        self.assertEqual(receipt["usage"], "missing")
        # A receipt of the wrong shape is a gap, not a value: a non-string id or a
        # non-dict usage is refused into "missing" rather than trusted.
        odd = json.dumps({"id": 7, "model": ["x"], "usage": "17 tokens",
                          "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, odd))
        self.assertIsNone(outcome["error"])
        receipt = self.provider.last_receipt
        self.assertEqual(receipt["response_id"], "missing")
        self.assertEqual(receipt["returned_model"], "missing")
        self.assertEqual(receipt["usage"], "missing")

    def test_meta_before_any_call_admits_the_receipt_is_missing(self):
        provider = proposal_ai.RemoteProvider("https://api.example.com", "m", self.KEY_ENV)
        self.assertEqual(provider.meta()["server_receipt"], "missing")

    def test_receipt_with_a_lone_surrogate_is_refused_before_evidence(self):
        # A1 (round 4): receipt values are server-controlled text; a lone surrogate used
        # to pass every isinstance check and crash evidence writing after the run
        # directory existed. The refusal must fire inside complete(), before anything.
        body = json.dumps({"id": "R-\ud800X",
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RECEIPT_ENCODING")
        self.assertIsNone(self.provider.last_receipt)

    def test_receipt_usage_with_a_surrogate_is_refused(self):
        payload = {"usage": {"note": "\ud800"}, "id": "ok",
                   "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}
        body = json.dumps(payload).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RECEIPT_ENCODING")

    def test_overlong_receipt_field_is_refused(self):
        body = json.dumps({"id": "x" * 300,
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RECEIPT_TOO_LONG")

    def test_receipt_echoing_the_key_is_refused(self):
        # A hostile endpoint can copy the Authorization value into any string it sends
        # back; a receipt that carried the key must never reach the evidence directory.
        body = json.dumps({"id": "Bearer secret-value",
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_ECHOES_KEY")
        self.assertIsNone(self.provider.last_receipt)

    def test_receipt_echo_inside_usage_is_refused_too(self):
        body = json.dumps({"usage": {"note": "secret-value"},
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_ECHOES_KEY")

    def test_echo_in_the_answer_body_is_refused(self):
        # F2: the model's answer is server-chosen text too. A credential echoed back
        # inside the content used to land in 02_raw_response.txt byte for byte.
        body = json.dumps({"choices": [{"message": {"content":
            "your key was secret-value\n" + proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_ECHOES_KEY")
        self.assertIsNone(self.provider.last_receipt)

    def test_echo_in_an_unrecognized_envelope_field_is_refused(self):
        # The containment runs against the whole wire payload: a side field the parser
        # never reads must not become a credential side channel either.
        body = json.dumps({"note": "secret-value", "choices": [
            {"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_ECHOES_KEY")

    def test_echo_inside_a_nested_usage_key_is_refused(self):
        # The echo check walks keys as well as values: json.dumps on the whole object
        # serialises keys too, and the walker collects them explicitly.
        body = json.dumps({"usage": {"secret-value": 1},
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RESPONSE_ECHOES_KEY")

    def test_deeply_nested_usage_is_refused_before_evidence(self):
        # F3: deep nesting fits in a couple of KB -- far under the 1 MiB cap -- and used
        # to crash provenance encoding after four evidence files were already on disk.
        # The depth here is chosen well below json.loads' own interpreter- and
        # stack-dependent limit, so the named refusal comes from the shape contract,
        # not from wherever the parser happens to blow up on this machine.
        deep = {"tokens": 1}
        for _ in range(300):
            deep = {"n": deep}
        body = json.dumps({"usage": deep, "id": "ok",
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        self.assertLess(len(body), 4096)
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RECEIPT_TOO_DEEP")
        self.assertIsNone(self.provider.last_receipt)

    def test_usage_one_level_past_the_bound_is_refused(self):
        usage = {"tokens": 1}
        for _ in range(proposal_ai.RECEIPT_USAGE_MAX_DEPTH + 1):
            usage = {"n": usage}
        body = json.dumps({"usage": usage,
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_RECEIPT_TOO_DEEP")

    def test_normal_usage_shape_still_passes(self):
        body = json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 7,
                                     "total_tokens": 17, "detail": {"source": "api"}},
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        _opener, outcome = self._run(_FakeResponse(200, body))
        self.assertIsNone(outcome["error"])
        self.assertEqual(self.provider.last_receipt["usage"]["total_tokens"], 17)

    def test_redirect_refusal_propagates_through_complete(self):
        _opener, outcome = self._run(proposal_ai.ProposalAIError("PROPOSAL_AI_REDIRECT_REFUSED", 302))
        self.assertEqual(outcome["error"].code, "PROPOSAL_AI_REDIRECT_REFUSED")


class EndToEndTest(unittest.TestCase):
    """Mock provider -> real catalogue -> real policy -> real four cores."""

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory(prefix="h56-ai-")
        root = Path(self._scratch.name)
        self._saved = (settings.RUNS_ROOT, settings.RECORDS_ROOT)
        settings.RUNS_ROOT = root / "runs"
        settings.RECORDS_ROOT = root / "records"
        settings.RUNS_ROOT.mkdir()
        settings.RECORDS_ROOT.mkdir()

    def tearDown(self):
        settings.RUNS_ROOT, settings.RECORDS_ROOT = self._saved
        self._scratch.cleanup()

    def _run(self, extra):
        argv = ["propose-ai", "--provider", "mock", "--business", "shop",
                "--stamp", "20261104T000000Z", "--host-key", "hostAI01"] + extra
        return app_main.main(argv), settings.RUNS_ROOT / "20261104T000000Z_shop"

    def test_valid_mock_proposal_runs_the_full_chain(self):
        code, run_dir = self._run([])
        self.assertEqual(code, app_main.EXIT_OK)
        # The AI node's evidence landed inside the run it feeds.
        ai_dir = run_dir / "ai_proposal"
        for name in ("01_prompt.txt", "02_raw_response.txt", "03_proposal.json",
                     "04_validation.json", "05_provenance.json"):
            self.assertTrue((ai_dir / name).is_file(), name)
        provenance = json.loads((ai_dir / "05_provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["provider"], "mock")
        self.assertEqual(provenance["proposal_source"], "ai_model")
        # The governance verdict on the model's own proposal.
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["decision"], "FEASIBLE")
        self.assertTrue(result["h56_invoked"])
        self.assertEqual(result["order"]["amount_source"], "CLIENT_SUPPLIED")
        self.assertEqual(result["order"]["amount_minor"], 2500)
        # The prompt carried the catalogue and no credential material.
        prompt = (ai_dir / "01_prompt.txt").read_text(encoding="utf-8")
        self.assertIn("S-C02", prompt)
        self.assertNotIn("PAYPAL_CLIENT_SECRET", prompt)

    def test_hallucinated_offer_is_blocked_before_the_kernel(self):
        code, run_dir = self._run(["--mock-response", _valid({"offer_id": "S-GHOST"})])
        self.assertEqual(code, app_main.EXIT_BLOCKED)
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertFalse(result["h56_invoked"])
        self.assertIn("POLICY_OFFER_NOT_IN_CATALOG", result["reason_codes"])
        self.assertTrue((run_dir / "ai_proposal" / "02_raw_response.txt").is_file())

    def test_wrong_amount_is_caught_by_the_price_rule(self):
        code, run_dir = self._run(["--mock-response", _valid({"amount_minor": 999})])
        self.assertEqual(code, app_main.EXIT_BLOCKED)
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        self.assertIn("POLICY_AMOUNT_NOT_CATALOGUE_PRICE", result["reason_codes"])

    def test_structurally_broken_model_text_leaves_no_run_directory(self):
        code, run_dir = self._run(["--mock-response", "sorry, no json today"])
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertFalse(run_dir.exists())

    def test_prompt_is_a_pure_function_of_the_catalogue(self):
        from app import policy
        catalog = policy.load_catalog()
        self.assertEqual(proposal_ai.build_prompt(catalog),
                         proposal_ai.build_prompt(policy.load_catalog()))

    def test_evidence_hashes_match_the_exact_file_bytes(self):
        # A multi-line model response: write_text would translate newlines on Windows
        # and make every registered hash disagree with its file. write_bytes must not.
        multi_line = "Here is the order:\n%s\nHope that helps." % _valid()
        code, run_dir = self._run(["--mock-response", multi_line])
        self.assertEqual(code, app_main.EXIT_OK)
        ai_dir = run_dir / "ai_proposal"
        provenance = json.loads((ai_dir / "05_provenance.json").read_text(encoding="utf-8"))
        import hashlib
        self.assertEqual(
            provenance["prompt_sha256"],
            hashlib.sha256((ai_dir / "01_prompt.txt").read_bytes()).hexdigest())
        self.assertEqual(
            provenance["raw_response_sha256"],
            hashlib.sha256((ai_dir / "02_raw_response.txt").read_bytes()).hexdigest())
        # The raw response on disk is byte-identical to what the model sent, newlines
        # included: LF stays LF.
        raw_text = (ai_dir / "02_raw_response.txt").read_bytes().decode("utf-8")
        self.assertEqual(raw_text, multi_line)
        self.assertIn("\n", raw_text)

    def test_invalid_stamp_is_refused_before_any_provider_call(self):
        # The ordering claim: an unusable run name costs zero model calls. The canary
        # provider would fail the test the moment it is constructed or called.
        class Canary:
            def __init__(self, *args, **kwargs):
                raise AssertionError("provider must not be constructed for a bad stamp")

        with mock.patch.object(proposal_ai, "RemoteProvider", Canary):
            argv = ["propose-ai", "--provider", "remote",
                    "--base-url", "https://api.example.com", "--model", "m",
                    "--business", "shop", "--stamp", "not-a-stamp"]
            code = app_main.main(argv)
        self.assertEqual(code, app_main.EXIT_USAGE)

    def test_invalid_business_is_refused_before_any_provider_call(self):
        class Canary:
            def __init__(self, *args, **kwargs):
                raise AssertionError("provider must not be constructed for a bad business")

        with mock.patch.object(proposal_ai, "RemoteProvider", Canary):
            argv = ["propose-ai", "--provider", "remote",
                    "--base-url", "https://api.example.com", "--model", "m",
                    "--business", "bad name!", "--stamp", "20261104T000000Z"]
            code = app_main.main(argv)
        self.assertEqual(code, app_main.EXIT_USAGE)

    def test_existing_run_directory_costs_zero_provider_calls(self):
        # R1: a legal but already-taken run target must be refused before the model is
        # asked for anything -- a live call spent to learn a local fact is a billed
        # request for nothing. The pre-existing directory is neither deleted nor reused.
        settings.run_directory("20261104T000000Z", "shop")
        taken_before = sorted(p.name for p in settings.RUNS_ROOT.iterdir())
        calls = []
        real = proposal_ai.MockProvider

        class Counting(real):
            def __init__(self, response=None):
                calls.append("constructed")
                super().__init__(response)

            def complete(self, prompt):
                calls.append("called")
                return super().complete(prompt)

        with mock.patch.object(proposal_ai, "MockProvider", Counting):
            code, run_dir = self._run([])
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertEqual(calls, [])
        # The directory that blocked the run is exactly as it was: untouched, unextended.
        self.assertEqual(sorted(p.name for p in settings.RUNS_ROOT.iterdir()), taken_before)
        self.assertFalse((run_dir / "ai_proposal").exists())

    def test_existing_run_directory_refusal_is_named_at_cli_level(self):
        settings.run_directory("20261104T000000Z", "shop")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code, _run_dir = self._run([])
        self.assertEqual(code, app_main.EXIT_USAGE)
        output = buffer.getvalue()
        self.assertIn("AI        REFUSED", output)
        self.assertIn("RUN_DIRECTORY_ALREADY_EXISTS", output)

    def test_reserved_key_env_is_a_named_cli_refusal(self):
        # R3: the class-level refusal (assertRaises in RemoteProviderRefusalTest) is not
        # the contract; the CLI must answer with the same named refusal, not a traceback.
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            argv = ["propose-ai", "--provider", "remote",
                    "--base-url", "https://api.example.com", "--model", "m",
                    "--key-env", "PAYPAL_CLIENT_SECRET",
                    "--business", "shop", "--stamp", "20261104T000000Z"]
            code = app_main.main(argv)
        self.assertEqual(code, app_main.EXIT_USAGE)
        output = buffer.getvalue()
        self.assertIn("AI        REFUSED", output)
        self.assertIn("PROPOSAL_AI_KEY_ENV_RESERVED", output)
        # The refusal happened before anything was created on the filesystem.
        self.assertFalse((settings.RUNS_ROOT / "20261104T000000Z_shop").exists())

    def test_lowercase_reserved_key_env_costs_zero_provider_calls(self):
        # F1 at the CLI layer: the case variant resolves to the same Windows variable.
        # The refusal lives in the constructor itself, so no canary patch here -- the
        # real constructor must refuse before any opener is built (zero network).
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            argv = ["propose-ai", "--provider", "remote",
                    "--base-url", "https://api.example.com", "--model", "m",
                    "--key-env", "paypal_client_secret",
                    "--business", "shop", "--stamp", "20261104T000000Z"]
            code = app_main.main(argv)
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertIn("PROPOSAL_AI_KEY_ENV_RESERVED", buffer.getvalue())
        self.assertFalse((settings.RUNS_ROOT / "20261104T000000Z_shop").exists())

    def _fake_remote_cli(self, body, key_env, key_value):
        """Run propose-ai against a fake opener that returns `body`; capture output."""
        saved = os.environ.get(key_env)
        os.environ[key_env] = key_value
        try:
            opener = _FakeOpener(_FakeResponse(200, body))
            with mock.patch("urllib.request.build_opener", return_value=opener):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    argv = ["propose-ai", "--provider", "remote",
                            "--base-url", "https://api.example.com", "--model", "m",
                            "--key-env", key_env,
                            "--business", "shop", "--stamp", "20261104T000000Z"]
                    code = app_main.main(argv)
        finally:
            if saved is None:
                os.environ.pop(key_env, None)
            else:
                os.environ[key_env] = saved
        return code, buffer.getvalue(), opener

    def test_key_echo_in_the_answer_body_is_refused_at_cli_level(self):
        # F2, repro 1: credential + newline + valid proposal in the answer body. Used to
        # exit 0 with the credential saved in 02_raw_response.txt.
        canary = "canarykey12345"
        body = json.dumps({"choices": [{"message": {"content":
            "your key was " + canary + "\n" + proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        code, output, opener = self._fake_remote_cli(
            body, "H56PAY_TEST_ECHO_KEY", canary)
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertIn("PROPOSAL_AI_RESPONSE_ECHOES_KEY", output)
        self.assertNotIn(canary, output)
        self.assertFalse((settings.RUNS_ROOT / "20261104T000000Z_shop").exists())
        self.assertIsNotNone(opener.opened)

    def test_escaped_key_echo_in_a_proposal_field_is_refused(self):
        # F2, repro 2, decoding gap: a credential containing a quote travels escaped on
        # the wire ("ab\"cd"), so the raw-body containment check passes -- but the
        # decoded payee heading for the proposal, the result, the binding and the
        # terminal carries it literally. Used to exit 0 FEASIBLE with the canary saved
        # into four files and printed on stdout.
        canary = 'ab"cd12'
        self.assertNotIn(canary, json.dumps({"payee": canary}))  # escaped on the wire
        body = json.dumps({"choices": [{"message": {"content":
            _valid({"payee": canary})}}]}).encode("utf-8")
        code, output, _opener = self._fake_remote_cli(
            body, "H56PAY_TEST_ESC_KEY", canary)
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertIn("PROPOSAL_AI_RESPONSE_ECHOES_KEY", output)
        self.assertNotIn(canary, output)
        self.assertFalse((settings.RUNS_ROOT / "20261104T000000Z_shop").exists())

    def test_deeply_nested_usage_refused_at_cli_level_with_no_directory(self):
        # F3 at the CLI layer: the deep-usage response must refuse by name with zero
        # evidence files, not crash provenance encoding after 01-04 landed. Depth 300
        # stays inside json.loads' own limits so the shape contract is what fires.
        deep = {"tokens": 1}
        for _ in range(300):
            deep = {"n": deep}
        body = json.dumps({"usage": deep,
                           "choices": [{"message": {"content": proposal_ai.MOCK_RESPONSE_DEFAULT}}]}).encode("utf-8")
        code, output, _opener = self._fake_remote_cli(
            body, "H56PAY_TEST_DEEP_KEY", "unused-key-value")
        self.assertEqual(code, app_main.EXIT_USAGE)
        self.assertIn("PROPOSAL_AI_RECEIPT_TOO_DEEP", output)
        self.assertFalse((settings.RUNS_ROOT / "20261104T000000Z_shop").exists())

    def test_evidence_encoding_failure_creates_no_directory(self):
        # The structural claim behind F3's fix: every evidence byte is serialized and
        # encoded before the directory is created, so an encoder crash cannot leave a
        # half-written evidence directory behind.
        run_dir = Path(self._scratch.name) / "encoding-failure"
        run_dir.mkdir()
        with mock.patch.object(proposal_ai.hostproof, "dumps", side_effect=RecursionError):
            with self.assertRaises(proposal_ai.ProposalAIError) as caught:
                proposal_ai.save_evidence(run_dir, "prompt", "raw",
                                          json.loads(proposal_ai.MOCK_RESPONSE_DEFAULT), {})
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_EVIDENCE_TOO_DEEP")
        self.assertFalse((run_dir / "ai_proposal").exists())


if __name__ == "__main__":
    unittest.main()
