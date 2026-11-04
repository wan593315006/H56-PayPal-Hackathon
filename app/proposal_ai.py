"""The AI proposal node (N1-13): a model proposes, governance disposes.

The demo chain before this module started from a controlled catalogue entry. This module
adds the missing first link: a language model drafts the payment proposal itself, and the
proposal then enters exactly the same chain as any other -- business policy first, the
four native cores after that, and PayPal only where every earlier layer allowed it.

Four boundaries hold the node inside the governance discipline:

* the model's output is a *proposal and nothing else*. It never carries a verdict: the
  words FEASIBLE or BLOCKED in model text are prose, and nothing here reads them. What
  the proposal becomes is decided by `policy.decide` and the kernel, on their own inputs.
* the raw model text is never trusted as JSON. The text must contain exactly one
  top-level JSON object -- not two, not one inside an array -- with no duplicated keys,
  exactly the proposal key set, and every field type- and character-checked. A model
  that adds a field, drops a field, sends a float amount, hides a newline in an
  identifier or repeats a key is refused by name before any catalogue, policy or kernel
  code runs.
* the credential never moves through argv, files, logs or evidence, and it never follows
  a redirect. `RemoteProvider` reads one environment variable whose *name* is a CLI
  argument; automatic redirect following is disabled outright, because urllib would
  replay the Authorization header against whatever host the 3xx names, on any scheme.
  A missing key is a named refusal before any socket is opened.
* evidence digests are computed over the exact bytes on disk. Text files are written
  with `write_bytes`, never `write_text`: on Windows the latter translates newlines,
  which would make every registered hash disagree with the file it names.

The offline path is exercised by `MockProvider`: a deterministic, socket-free provider
whose responses the tests can make valid or broken at will. The live path
(`RemoteProvider`) speaks the OpenAI-compatible `/chat/completions` shape over HTTPS,
sends an explicit output cap, reads a bounded response, and is reached only when a Human
has placed a key in the environment.
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.request

from . import hostproof, settings

# The closed key set of a proposal. Exactly these, exactly no others: an extra field from
# the model must be a refusal, not a silent passenger that later rides into a digest.
PROPOSAL_KEYS = ("offer_id", "order_id", "amount_minor", "currency", "payee")

PROPOSAL_EVIDENCE_SCHEMA = "H56_AI_PROPOSAL_EVIDENCE_V1"

# Structural field limits. order_id is model-invented, so its shape is pinned to what the
# prompt promises; the other strings only have to be short, clean, control-char-free text.
ORDER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
FIELD_MAX_CHARS = 128
_CONTROL_CHARS = frozenset(chr(code) for code in range(0x20)) | {"\x7f"}

# The response body is server-controlled text; a cap keeps a runaway peer from turning
# one proposal call into unbounded memory.
MAX_RESPONSE_BYTES = 1 << 20

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


def _scan_top_level(text):
    """String-aware scan of the whole text for top-level JSON structure.

    Returns (object_spans, array_seen). Bracket counting treats string literals as
    opaque: a brace, bracket or quote inside a string, and an escaped quote, change
    nothing. Unbalanced brackets anywhere are a refusal -- a stray closing bracket in
    prose is not something a compliant answer contains, and guessing past it would be
    choosing which parts of model output to ignore.
    """
    spans = []
    array_seen = False
    depth = 0
    object_start = None
    in_string = False
    escaped = False
    for index, char in enumerate(text):
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
            if depth == 0:
                object_start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ProposalAIError("PROPOSAL_AI_UNBALANCED_OBJECT")
            if depth == 0 and object_start is not None:
                spans.append((object_start, index + 1))
                object_start = None
        elif char == "[":
            if depth == 0:
                array_seen = True
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                raise ProposalAIError("PROPOSAL_AI_UNBALANCED_OBJECT")
    if depth != 0 or in_string or object_start is not None:
        raise ProposalAIError("PROPOSAL_AI_UNBALANCED_OBJECT")
    return spans, array_seen


def extract_json_object(text):
    """The exactly-one top-level JSON object in `text`, or a named refusal.

    Zero objects is a refusal; two or more is a refusal; one wrapped in an array is a
    refusal; an array anywhere at top level is a refusal. Prose around the object stays
    tolerated, but prose carrying square brackets is not -- the answer must not contain
    structure the proposal schema does not define.
    """
    if type(text) is not str:
        raise ProposalAIError("PROPOSAL_AI_NO_JSON_OBJECT", type(text).__name__)
    spans, array_seen = _scan_top_level(text)
    if array_seen:
        raise ProposalAIError("PROPOSAL_AI_ARRAY_WRAPPED")
    if not spans:
        raise ProposalAIError("PROPOSAL_AI_NO_JSON_OBJECT", "no top-level object")
    if len(spans) > 1:
        raise ProposalAIError("PROPOSAL_AI_MULTIPLE_OBJECTS", len(spans))
    start, end = spans[0]
    return text[start:end]


def _reject_float(value):
    raise ProposalAIError("PROPOSAL_AI_FLOAT_AMOUNT", value)


def _object_pairs(pairs):
    """json.loads object_pairs_hook: the last duplicate key must not silently win."""
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise ProposalAIError("PROPOSAL_AI_DUPLICATE_KEY", key)
        seen.add(key)
    return dict(pairs)


# A structural ceiling on the amount, far above every catalogue price: a model cannot
# make the pipeline carry an arbitrarily huge integer through hashing and serialisation
# on its way to a refusal that policy would issue anyway.
AMOUNT_MAX = 10 ** 15


def _check_field(key, value):
    # Surrogates matter: json.loads accepts a lone surrogate escaped as \\ud800, but no
    # UTF-8 byte encoding of it exists, so the value would explode later -- at evidence
    # write time, leaving a half-written directory. A proposal that cannot survive
    # UTF-8 encoding is not a proposal; it is a refusal.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ProposalAIError("PROPOSAL_AI_FIELD_ENCODING", key) from None
    if any(char in _CONTROL_CHARS for char in value) or value != value.strip():
        raise ProposalAIError("PROPOSAL_AI_FIELD_CHARS", key)
    if len(value) > FIELD_MAX_CHARS:
        raise ProposalAIError("PROPOSAL_AI_FIELD_TOO_LONG", key)


def parse_proposal(text):
    """Strict structural validation. The catalogue and policy stay downstream of this."""
    raw = extract_json_object(text)
    try:
        document = json.loads(raw, parse_float=_reject_float,
                              object_pairs_hook=_object_pairs)
    except ProposalAIError:
        raise
    except RecursionError:
        raise ProposalAIError("PROPOSAL_AI_JSON_TOO_DEEP") from None
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
    for key in ("offer_id", "order_id", "currency", "payee"):
        _check_field(key, document[key])
    if not ORDER_ID_PATTERN.fullmatch(document["order_id"]):
        raise ProposalAIError("PROPOSAL_AI_ORDER_ID_INVALID", repr(document["order_id"])[:40])
    amount = document["amount_minor"]
    if type(amount) is not int or type(amount) is bool:
        raise ProposalAIError("PROPOSAL_AI_AMOUNT_TYPE", repr(amount)[:40])
    if amount <= 0 or amount > AMOUNT_MAX:
        raise ProposalAIError("PROPOSAL_AI_AMOUNT_VALUE", amount)
    return document


class MockProvider:
    """A deterministic, socket-free stand-in for the live model. Tests drive its text."""

    name = "mock"

    def __init__(self, response=None):
        self._response = MOCK_RESPONSE_DEFAULT if response is None else response

    def complete(self, _prompt):
        return self._response

    def assert_no_echo(self, _text):
        """No credential is ever involved on the mock path; nothing to refuse."""
        return None

    def meta(self):
        return {"provider": self.name, "deterministic": True}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect outright.

    urllib's default opener replays the Authorization header against the redirect
    target, whatever host and scheme it names -- a 30x would move the key off the
    endpoint the Human configured. A chained-call API has no reason to redirect a POST
    with credentials, so the only safe number of automatic redirects is zero. Raising
    here (instead of returning None) surfaces a named code instead of a bare HTTPError.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProposalAIError("PROPOSAL_AI_REDIRECT_REFUSED", code)


class RemoteProvider:
    """OpenAI-compatible chat completions over HTTPS. Fail-closed, key-quiet.

    The key is read from the environment at call time, sent only in the Authorization
    header, and never written anywhere: not to evidence, not to logs, not into an error
    message. Redirects are refused by `_NoRedirect`. HTTP failures report the status
    code alone: a response body is server-controlled text and has no place in a named
    refusal. The request states an explicit output cap and the response read is bounded,
    so neither direction of the call is unbounded.
    """

    name = "remote"
    DEFAULT_MAX_OUTPUT_TOKENS = 512

    def __init__(self, base_url, model, key_env, timeout_seconds=60,
                 max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS):
        # The model credential lives under its own name. A key_env naming one of the
        # .env-managed PayPal keys would route a PayPal secret through the model
        # transport -- a smuggle channel, not a configuration. The comparison is on
        # canonical (upper) forms: Windows resolves environment names case-insensitively,
        # so `paypal_client_secret` reads the same variable as `PAYPAL_CLIENT_SECRET`,
        # and a case variant must be refused exactly like the spelling it resolves to.
        if settings.is_reserved_env_key(key_env):
            raise ProposalAIError("PROPOSAL_AI_KEY_ENV_RESERVED", key_env)
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.key_env = key_env
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.elapsed_ms = None
        # The server's own account of the last successful call -- id, model echo,
        # usage, status and a digest of the exact response bytes. `None` until a call
        # succeeds; a failed call refuses by name and leaves nothing half-recorded.
        self.last_receipt = None
        # The credential of the last completed call, kept for the command layer's
        # post-parse echo check (assert_no_echo). The value is already resident in the
        # process environment for the life of the process; this reference adds no
        # exposure and is never logged, never written, never evidenced.
        self._last_key = None

    def assert_no_echo(self, text):
        """Refuse text that carries the credential this provider last used.

        The command layer calls this on the parsed proposal before anything is printed,
        saved or evaluated: a credential that survives into an order field would ride
        into result.json, the binding file and the terminal -- through the front door,
        no redirect required. JSON escaping makes this check necessary in addition to
        the raw-body check in `complete`: a credential containing a quote travels as
        `\\"` on the wire, so the raw text never contains it literally while the decoded
        field value does.
        """
        if self._last_key and self._last_key in text:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_ECHOES_KEY")

    def _request(self, prompt, key):
        """Build the POST request. Exposed for tests: no socket is opened here."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
            "max_tokens": self.max_output_tokens,
        }).encode("utf-8")
        return urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
            method="POST")

    def complete(self, prompt):
        if not self.base_url.startswith("https://"):
            raise ProposalAIError("PROPOSAL_AI_INSECURE_ENDPOINT", self.base_url)
        key = settings.credential(self.key_env)
        if key is None:
            raise ProposalAIError("PROPOSAL_AI_CREDENTIALS_MISSING", self.key_env)
        self._last_key = key
        request = self._request(prompt, key)
        opener = urllib.request.build_opener(_NoRedirect)
        started = time.monotonic()
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                status = response.status
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except ProposalAIError:
            raise
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
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_TOO_LARGE", len(payload))
        try:
            document = json.loads(payload.decode("utf-8"))
            content = document["choices"][0]["message"]["content"]
        except RecursionError:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_UNPARSEABLE",
                                  "RecursionError") from None
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_UNPARSEABLE",
                                  type(error).__name__) from None
        if type(content) is not str or not content.strip():
            raise ProposalAIError("PROPOSAL_AI_EMPTY_CHOICE")
        # The answer body is server-chosen text, exactly like the receipt fields: a
        # credential echoed back inside the content would land in the raw-response
        # evidence file byte for byte, and -- parsed -- ride into the proposal, the
        # result and the binding. The threat model for echoes always covered the
        # server; the answer is the server speaking too.
        if key in content:
            raise ProposalAIError("PROPOSAL_AI_RESPONSE_ECHOES_KEY")
        # The receipt is what the server said about the call, kept beside the content
        # it describes: id, model echo and usage are what a bill or an audit asks for,
        # and the digest is taken over the exact bytes that arrived. A field the server
        # omitted is "missing", never fabricated -- a receipt that guesses is worse
        # than one that admits a gap. Every value the server chose is checked before
        # it is stored: an unencodable or overlong string must refuse the call here,
        # not crash evidence writing after the run directory exists.
        receipt = {
            "http_status": status,
            "response_bytes": len(payload),
            "response_sha256": hashlib.sha256(payload).hexdigest(),
            "response_id": _receipt_text(document, "id"),
            "returned_model": _receipt_text(document, "model"),
            "usage": document.get("usage")
            if isinstance(document.get("usage"), dict) else "missing",
        }
        _check_receipt(receipt, key)
        self.last_receipt = receipt
        return content

    def meta(self):
        """Configured facts plus the last call's server receipt, never a key value.

        `configured_model` is what the Human asked for; `returned_model` is what the
        server claims it ran. They are recorded separately because agreeing is an
        observation, not an assumption.
        """
        receipt = self.last_receipt if self.last_receipt is not None else "missing"
        returned = self.last_receipt["returned_model"] if self.last_receipt else "missing"
        return {"provider": self.name, "configured_model": self.model,
                "returned_model": returned, "base_url": self.base_url,
                "key_env": self.key_env, "elapsed_ms": self.elapsed_ms,
                "server_receipt": receipt}


RECEIPT_TEXT_MAX_CHARS = 256


def _receipt_text(document, key):
    """A receipt field that must be a short, encodable, non-empty string -- else refusal.

    Receipt values are server-controlled text, exactly like proposal fields: a lone
    surrogate would pass every isinstance check and then crash evidence writing after
    the run directory exists (the failure shape the first review caught for proposal
    fields, arriving here through a new channel). The same named refusal fires before
    anything is stored, and "missing" stays reserved for fields the server omitted.
    """
    value = document.get(key)
    if not isinstance(value, str) or not value:
        return "missing"
    if len(value) > RECEIPT_TEXT_MAX_CHARS:
        raise ProposalAIError("PROPOSAL_AI_RECEIPT_TOO_LONG", key)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ProposalAIError("PROPOSAL_AI_RECEIPT_ENCODING", key) from None
    return value


RECEIPT_USAGE_MAX_DEPTH = 8
RECEIPT_USAGE_MAX_NODES = 64


def _check_receipt(receipt, key):
    """Bound the usage object and keep the one credential out of every receipt string.

    A hostile or broken endpoint can copy the Authorization header into any string it
    returns; a receipt that carried the key would breach the module's never-in-evidence
    invariant through the server's own mouth. The echo check is containment against the
    one key this call used -- cheap, exact, and fail-closed.

    `usage` gets an explicit shape contract instead of a hoping-it-encodes shrug: its
    nesting depth and node count are bounded, every string in it (keys included) is
    encode-checked, and all of it happens here -- inside `complete`, before any run
    directory exists. A deeply nested usage once crashed provenance encoding *after*
    four evidence files were already on disk (a ~2 KB response was enough); the bounds
    make that state unreachable rather than merely unlikely.
    """
    usage = receipt["usage"]
    strings = [receipt["response_id"], receipt["returned_model"]]
    if isinstance(usage, dict):
        count = 0

        def walk(value, depth):
            nonlocal count
            count += 1
            if count > RECEIPT_USAGE_MAX_NODES:
                raise ProposalAIError("PROPOSAL_AI_RECEIPT_TOO_LARGE", "usage")
            if depth > RECEIPT_USAGE_MAX_DEPTH:
                raise ProposalAIError("PROPOSAL_AI_RECEIPT_TOO_DEEP", depth)
            if isinstance(value, dict):
                for inner_key, inner in value.items():
                    strings.append(inner_key)
                    walk(inner, depth + 1)
            elif isinstance(value, list):
                for inner in value:
                    walk(inner, depth + 1)
            elif isinstance(value, str):
                strings.append(value)

        try:
            walk(usage, 0)
        except RecursionError:
            # A depth the walker itself cannot express is a depth evidence encoding
            # could not survive either: refuse it by name, before any directory.
            raise ProposalAIError("PROPOSAL_AI_RECEIPT_TOO_DEEP",
                                  "beyond-walker") from None
        for text in strings:
            if not isinstance(text, str):
                continue
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                raise ProposalAIError("PROPOSAL_AI_RECEIPT_ENCODING",
                                      "usage") from None
    if key and any(key in text for text in strings):
        raise ProposalAIError("PROPOSAL_AI_RESPONSE_ECHOES_KEY")


def check_encodable(text):
    """Named refusal for text that has no UTF-8 form (a lone surrogate, most commonly).

    Callers that create a run directory use this before creating anything, so a bad
    model response costs zero directories. `save_evidence` re-runs the same check as
    the last line of defence.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ProposalAIError("PROPOSAL_AI_EVIDENCE_ENCODING",
                              type(error).__name__) from None
    return text


def save_evidence(run_directory, prompt, raw_response, proposal, provider_meta):
    """Land the whole AI node's evidence inside the run directory it feeds.

    Five files, in review order: the prompt, the untouched model text, the parsed
    proposal, the validation report, and the provenance record. Provenance carries
    digests computed over the exact bytes written to disk -- a hash that disagrees with
    its file is worse than no hash, so the newline translation `write_text` performs on
    Windows is deliberately bypassed. Provenance carries digests, not text: the raw
    model response stays reviewable beside its own hash without anything here deciding
    which part of it is "safe to quote".

    Every byte is serialized and encoded *before* the directory is created. A response
    that cannot become evidence -- a lone surrogate, or a structure too deep for the
    encoder -- is a named refusal that costs zero directories, instead of a crash that
    leaves files 01-04 on disk without the provenance that hashes them.
    """
    prompt_bytes = check_encodable(prompt).encode("utf-8")
    raw_bytes = check_encodable(raw_response).encode("utf-8")
    checks = {
        "schema": PROPOSAL_EVIDENCE_SCHEMA,
        "keys_expected": list(PROPOSAL_KEYS),
        "keys_received": sorted(proposal),
        "key_set_exact": sorted(proposal) == sorted(PROPOSAL_KEYS),
        "amount_is_int": type(proposal["amount_minor"]) is int,
        "all_fields_typed": all(type(proposal[key]) is str and proposal[key]
                                for key in ("offer_id", "order_id", "currency", "payee")),
    }
    provenance = None
    try:
        provenance = dict(provider_meta)
        provenance.update({
            "schema": PROPOSAL_EVIDENCE_SCHEMA,
            "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "raw_response_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "proposal_sha256": hashlib.sha256(
                hostproof.dumps(proposal).encode("utf-8")).hexdigest(),
            "proposal_source": "ai_model",
        })
        files = {
            "01_prompt.txt": prompt_bytes,
            "02_raw_response.txt": raw_bytes,
            "03_proposal.json": hostproof.dumps(proposal).encode("utf-8"),
            "04_validation.json": hostproof.dumps(checks).encode("utf-8"),
            "05_provenance.json": hostproof.dumps(provenance).encode("utf-8"),
        }
    except RecursionError:
        # The shape bounds in _check_receipt make this unreachable for provider data;
        # it stands as the named last line instead of a bare traceback.
        raise ProposalAIError("PROPOSAL_AI_EVIDENCE_TOO_DEEP",
                              "evidence encoding") from None
    directory = run_directory / "ai_proposal"
    directory.mkdir()
    for name, payload in files.items():
        directory.joinpath(name).write_bytes(payload)
    return provenance
