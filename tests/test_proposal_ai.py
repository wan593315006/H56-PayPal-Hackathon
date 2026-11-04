"""The AI proposal node: structural refusals, mock-driven end-to-end runs, key quietness.

Every network-facing claim is tested against the MockProvider or against refusals that
fire before any socket call. The offline network guard installed by run_offline_tests.py
is the backstop: if any code path here opened a socket, the whole suite would fail, not
just one case.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

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
        text = _valid({"order_id": 'O-"X"-{weird}-1'})
        proposal = proposal_ai.parse_proposal(text)
        self.assertEqual(proposal["order_id"], 'O-"X"-{weird}-1')

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

    def test_array_is_not_an_object(self):
        # A bare array has no brace at all, so the scanner refuses it before parsing.
        with self.assertRaises(proposal_ai.ProposalAIError) as caught:
            proposal_ai.parse_proposal('[1, 2, 3]')
        self.assertEqual(caught.exception.code, "PROPOSAL_AI_NO_JSON_OBJECT")

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


if __name__ == "__main__":
    unittest.main()
