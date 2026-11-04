"""The AI proposal node (N1-13): a model proposes, governance disposes.

The demo chain before this module started from a controlled catalogue entry. This module
adds the missing first link: a language model drafts the payment proposal itself, and the
proposal then enters exactly the same chain as any other -- business policy first, the
four native cores after that, and PayPal only where every earlier layer allowed it.

Three boundaries hold the node inside the governance discipline:

* the model's output is a *proposal and nothing else*. It never carries a verdict: the
  words FEASIBLE or BLOCKED in model text are prose, and nothing here reads them. What
  the proposal becomes is decided by `policy.decide` and the kernel, on their own inputs.
* the raw model text is never trusted as JSON. It is scanned for one JSON object, the
  object must carry exactly the proposal key set -- no fewer, no more -- and every field
  is type-checked. A model that adds a field, drops a field, or sends a float amount is
  refused by name before any catalogue, policy or kernel code runs.
* the credential never moves through argv, files, logs or evidence. `RemoteProvider`
  reads one environment variable whose *name* is a CLI argument; only that name, never
  the value, can appear in an error or a provenance record. A missing key is a named
  refusal before any socket is opened.

The offline path is exercised by `MockProvider`: a deterministic, socket-free provider
whose responses the tests can make valid or broken at will. The live path
(`RemoteProvider`) speaks the OpenAI-compatible `/chat/completions` shape over HTTPS and
is reached only when a Human has placed a key in the environment.
"""
import hashlib
import json
import time
import urllib.error
import urllib.request

from . import hostproof, settings

# The closed key set of a proposal. Exactly these, exactly no others: an extra field from
# the model must be a refusal, not a silent passenger that later rides into a digest.
PROPOSAL_KEYS = ("offer_id", "order_id", "amount_minor", "currency", "payee")

PROPOSAL_EVIDENCE_SCHEMA = "H56_AI_PROPOSAL_EVIDENCE_V1"

# The default mock response: a proposal that names a real catalogue offer and states the
# catalogue's own numbers. Policy will allow it; the kernel decides after that. The mock
# exists so the whole node is testable with zero network and zero credentials.
MOCK_RESPONSE_DEFAULT = json.dumps({
    "offer_id": "S-C02",
    "order_id": "O-AI-DEMO-1",
    "amount_minor": 2500,
    "currency": "USD",
    "payee": "PAYPAL-MERCHANT-SANDBOX-001",
}, sort_keys=True)

PROMPT_TEMPLATE = """You are the proposal link of a payment governance pipeline.
Choose ONE item from the catalogue below and draft the payment order for it.

Catalogue (the authoritative price list; the pipeline re-checks every number you state):
%s

Answer with EXACTLY ONE JSON object and nothing else -- no prose before or after, no
markdown fences. The object must have exactly these keys and no others:
  "offer_id", "order_id", "amount_minor", "currency", "payee"
Rules:
- "offer_id" and "payee" must be copied from the catalogue.
- "amount_minor" must be an integer in minor units (cents), equal to the catalogue price.
- "currency" must be the catalogue currency of that offer.
- "order_id" must be a short identifier you invent, matching [A-Za-z0-9_-]+.
Do NOT state or imply any approval decision. Whether this payment may proceed is decided
entirely by the governance layers that run after you.
"""


class ProposalAIError(RuntimeError):
    """Every refusal here is named: the caller prints the code, never a stack trace."""

    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def build_prompt(catalog):
    """The prompt carries the catalogue interface, nothing secret and nothing else."""
    return PROMPT_TEMPLATE % json.dumps(catalog, indent=2, sort_keys=True)


def extract_json_object(text):
    """Return the first balanced top-level JSON object in `text`, or refuse by name.

    Brace counting is string-aware: a brace inside a JSON string literal, and a brace
    escaped inside one, do not open or close the object. Prose around the object is
    tolerated -- models add it despite instructions -- but zero or several top-level
    objects is a refusal, not a best guess.
    """
    if type(text) is not str:
        raise ProposalAIError("PROPOSAL_AI_NO_JSON_OBJECT", type(text).__name__)
    start = text.find("{")
    if start < 0:
        raise ProposalAIError("PROPOSAL_AI_NO_JSON_OBJECT", "no opening brace")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ProposalAIError("PROPOSAL_AI_UNBALANCED_OBJECT")


def _reject_float(value):
    raise ProposalAIError("PROPOSAL_AI_FLOAT_AMOUNT", value)


def parse_proposal(text):
    """Strict structural validation. The catalogue and policy stay downstream of this."""
    raw = extract_json_object(text)
    try:
        document = json.loads(raw, parse_float=_reject_float)
    except ProposalAIError:
        raise
    except ValueError as error:
        raise ProposalAIError("PROPOSAL_AI_MALFORMED_JSON", str(error)[:120]) from None
    if type(document) is not dict:
        raise ProposalAIError("PROPOSAL_AI_NOT_OBJECT", type(document).__name__)
    expected = set(PROPOSAL_KEYS)
    received = set(document)
    if received != expected:
        missing = sorted(expected - received)
        extra = sorted(received - expected)
        raise ProposalAIError("PROPOSAL_AI_KEY_SET_MISMATCH",
                              "missing=%s extra=%s" % (missing or "-", extra or "-"))
    for key in ("offer_id", "order_id", "currency", "payee"):
        if type(document[key]) is not str or not document[key]:
            raise ProposalAIError("PROPOSAL_AI_FIELD_TYPE", key)
    amount = document["amount_minor"]
    if type(amount) is not int or type(amount) is bool:
        raise ProposalAIError("PROPOSAL_AI_AMOUNT_TYPE", repr(amount)[:40])
    if amount <= 0:
        raise ProposalAIError("PROPOSAL_AI_AMOUNT_VALUE", amount)
    return document


class MockProvider:
    """A deterministic, socket-free stand-in for the live model. Tests drive its text."""

    name = "mock"

    def __init__(self, response=None):
        self._response = MOCK_RESPONSE_DEFAULT if response is None else response

    def complete(self, _prompt):
        return self._response

    def meta(self):
        return {"provider": self.name, "deterministic": True}


class RemoteProvider:
    """OpenAI-compatible chat completions over HTTPS. Fail-closed, key-quiet.

    The key is read from the environment at call time, sent only in the Authorization
    header, and never written anywhere: not to evidence, not to logs, not into an error
    message. HTTP failures report the status code alone: a response body is
    server-controlled text and has no place in a named refusal.
    """

    name = "remote"

    def __init__(self, base_url, model, key_env, timeout_seconds=60):
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.key_env = key_env
        self.timeout_seconds = timeout_seconds
        self.elapsed_ms = None

    def complete(self, prompt):
        if not self.base_url.startswith("https://"):
            raise ProposalAIError("PROPOSAL_AI_INSECURE_ENDPOINT", self.base_url)
        key = settings.credential(self.key_env)
        if key is None:
            raise ProposalAIError("PROPOSAL_AI_CREDENTIALS_MISSING", self.key_env)
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
            method="POST")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = response.status
                payload = response.read()
        except urllib.error.HTTPError as error:
            raise ProposalAIError("PROPOSAL_AI_HTTP_STATUS", error.code) from None
        except urllib.error.URLError as error:
            raise ProposalAIError("PROPOSAL_AI_TRANSPORT", str(error.reason)[:120]) from None
        except OSError as error:
            raise ProposalAIError("PROPOSAL_AI_TRANSPORT", str(error)[:120]) from None
        finally:
            self.elapsed_ms = int((time.monotonic() - started) * 1000)
        if status != 200:
            raise ProposalAIError("PROPOSAL_AI_HTTP_STATUS", status)
        try:
            document = json.loads(payload.decode("utf-8"))
            content = document["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_UNPARSEABLE",
                                  type(error).__name__) from None
        if type(content) is not str or not content.strip():
            raise ProposalAIError("PROPOSAL_AI_EMPTY_CHOICE")
        return content

    def meta(self):
        return {"provider": self.name, "model": self.model, "base_url": self.base_url,
                "key_env": self.key_env, "elapsed_ms": self.elapsed_ms}


def save_evidence(run_directory, prompt, raw_response, proposal, provider_meta):
    """Land the whole AI node's evidence inside the run directory it feeds.

    Five files, in review order: the prompt, the untouched model text, the parsed
    proposal, the validation report, and the provenance record. Provenance carries
    digests, not text: the raw model response stays reviewable beside its own hash
    without anything here deciding which part of it is "safe to quote".
    """
    directory = run_directory / "ai_proposal"
    directory.mkdir()
    checks = {
        "schema": PROPOSAL_EVIDENCE_SCHEMA,
        "keys_expected": list(PROPOSAL_KEYS),
        "keys_received": sorted(proposal),
        "key_set_exact": sorted(proposal) == sorted(PROPOSAL_KEYS),
        "amount_is_int": type(proposal["amount_minor"]) is int,
        "all_fields_typed": all(type(proposal[key]) is str and proposal[key]
                                for key in ("offer_id", "order_id", "currency", "payee")),
    }

    def _write_json(name, document):
        directory.joinpath(name).write_bytes(hostproof.dumps(document).encode("utf-8"))

    directory.joinpath("01_prompt.txt").write_text(prompt, encoding="utf-8")
    directory.joinpath("02_raw_response.txt").write_text(raw_response, encoding="utf-8")
    _write_json("03_proposal.json", proposal)
    _write_json("04_validation.json", checks)
    provenance = dict(provider_meta)
    provenance.update({
        "schema": PROPOSAL_EVIDENCE_SCHEMA,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "raw_response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
        "proposal_sha256": hashlib.sha256(
            hostproof.dumps(proposal).encode("utf-8")).hexdigest(),
        "proposal_source": "ai_model",
    })
    _write_json("05_provenance.json", provenance)
    return provenance
