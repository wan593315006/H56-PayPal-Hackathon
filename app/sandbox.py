"""PayPal Sandbox order flow: create, read, approval state, capture.

What this module is allowed to know, and what it is not:

* the sandbox host and no other host. `base_url` has exactly one entry, and
  `refuse_production` runs both on the value it returns and on every URL built from it.
  This matters more than it looks: measured from this machine, `api-m.paypal.com` is
  reachable, so "sandbox" cannot be an ambient default that a typo falls back to.
* the amount as an integer count of minor units, formatted once, by integer division.
  `amount_value` refuses bools, floats, strings, zero and negatives. No code path in
  this module ever divides into a float, because `str(minor / 100)` is right for most
  values and wrong in exactly the cases nobody tests.
* the buyer's authorization as PayPal reports it. This is never the same fact as H56's
  verdict, and `capture_preconditions` reads only the PayPal status. A `FEASIBLE`
  governance decision means the order is admissible under the catalogue rules; it does
  not mean the payer agreed to pay, and no amount of it will satisfy the precondition.
  The verdict is carried into the record *beside* the state, never in place of it.

Credentials are read from the process environment at the moment of use and are never
stored, echoed, or written. This module is loadable and testable with no credentials and
no network: every HTTP call goes through `Transport`, and the mock transport is a full
implementation, not a stub.
"""
import base64
import datetime
import hashlib
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

from . import settings

SCHEMA = "H56_PAYPAL_SANDBOX_V1"
INTERFACE = "1.0.0"

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
API_HOST = "api-m.sandbox.paypal.com"

# Closed on purpose. There is no `production` entry, so `base_url("production")` refuses
# rather than returning the live host and letting a caller decide what to do about it.
ENVIRONMENTS = {"sandbox": SANDBOX_BASE}

TOKEN_PATH = "/v1/oauth2/token"
ORDERS_PATH = "/v2/checkout/orders"

FORM_TYPE = "application/x-www-form-urlencoded"
JSON_TYPE = "application/json"

REQUEST_TIMEOUT = 25
MAX_RESPONSE_BYTES = 262144

# The freshness contract (施工方案 §7, restored by the P3.2 audit): an evaluation is
# usable for at most 300 seconds from its own `as_of`, measured against the real wall
# clock at the moment of execution, and a timestamp dated in the future is not evidence
# at all. The previous bound here was 86400 seconds -- a day -- which is why the auditor
# measured a 602-second-old evaluation passing the gate. Past the bound the flow turns to
# a real re-evaluation under a fresh snapshot; timestamps are never stretched to fit.
MAX_EVALUATION_AGE_SECONDS = 300
# The business proposal -- what is being bought, at what price, to whom -- holds for
# 900 seconds from the moment it was confirmed. A re-evaluation past the 300-second
# freshness bound may still continue the same operation inside this window; past it the
# proposal itself must be confirmed again, and no order is created or captured.
PROPOSAL_WINDOW_SECONDS = 900

SANDBOX_HOST_REFUSED = "SANDBOX_HOST_REFUSED"
ENVIRONMENT_UNKNOWN = "SANDBOX_ENVIRONMENT_UNKNOWN"
AMOUNT_INVALID = "SANDBOX_AMOUNT_INVALID"
CALLBACK_INVALID = "SANDBOX_CALLBACK_INVALID"
RESPONSE_UNREADABLE = "SANDBOX_RESPONSE_UNREADABLE"
RESPONSE_REFUSED = "SANDBOX_RESPONSE_REFUSED"
ORDER_STATE_UNEXPECTED = "SANDBOX_ORDER_STATE_UNEXPECTED"
PAYER_NOT_APPROVED = "SANDBOX_PAYER_NOT_APPROVED"
CAPTURE_AMOUNT_MISMATCH = "SANDBOX_CAPTURE_AMOUNT_MISMATCH"
CAPTURE_CURRENCY_MISMATCH = "SANDBOX_CAPTURE_CURRENCY_MISMATCH"
CAPTURE_MISSING = "SANDBOX_CAPTURE_MISSING"
CAPTURE_PENDING = "SANDBOX_CAPTURE_PENDING"
ORDER_MISMATCH = "SANDBOX_ORDER_MISMATCH"
KEY_SEED_INVALID = "SANDBOX_COMMIT_KEY_SEED_INVALID"
OPERATION_ID_INVALID = "SANDBOX_OPERATION_ID_INVALID"
TRANSPORT_REFUSED = "SANDBOX_TRANSPORT_REFUSED"
REDIRECT_REFUSED = "SANDBOX_REDIRECT_REFUSED"
INTENT_MISMATCH = "SANDBOX_INTENT_MISMATCH"
EVALUATION_TIMESTAMP_INVALID = "SANDBOX_EVALUATION_TIMESTAMP_INVALID"
H56_RECORD_MISSING = "SANDBOX_H56_RECORD_MISSING"
H56_RECORD_UNAVAILABLE = "SANDBOX_H56_RECORD_UNAVAILABLE"
H56_ORDER_MISMATCH = "SANDBOX_H56_ORDER_MISMATCH"
H56_BINDING_INVALID = "SANDBOX_H56_BINDING_INVALID"
H56_DECISION_NOT_FEASIBLE = "SANDBOX_H56_DECISION_NOT_FEASIBLE"
H56_EVALUATION_STALE = "SANDBOX_H56_EVALUATION_STALE"
H56_EVALUATION_FUTURE = "SANDBOX_H56_EVALUATION_FUTURE"
PROPOSAL_EXPIRED = "SANDBOX_PROPOSAL_EXPIRED"
RUN_STATE_UNKNOWN = "SANDBOX_RUN_STATE_UNKNOWN"

CREATED = "CREATED"
APPROVED = "APPROVED"
COMPLETED = "COMPLETED"
CAPTURE_READY = "CAPTURE_READY"
ALREADY_CAPTURED = "ALREADY_CAPTURED"


class SandboxError(RuntimeError):
    """Every refusal carries a code. A message alone is not a result."""

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = str(detail)
        super().__init__(code + (": " + self.detail if self.detail else ""))


# ---------------------------------------------------------------- environment and host


def base_url(environment=None):
    """The one place a host is chosen. Unknown environment refuses; known one re-checks.

    No trimming and no case folding. `PAYPAL_ENVIRONMENT=Sandbox` and `sandbox ` are both
    refused, because a name that has to be repaired before it can be compared is a name
    that was written by accident, and the repair is the only thing standing between an
    accident and a request.
    """
    if environment is None:
        environment = os.environ.get("PAYPAL_ENVIRONMENT", "sandbox")
    if environment not in ENVIRONMENTS:
        raise SandboxError(ENVIRONMENT_UNKNOWN,
                           "%r (allowed: %s)" % (environment, ", ".join(sorted(ENVIRONMENTS))))
    url = ENVIRONMENTS[environment]
    refuse_production(url)
    return url


def refuse_production(url):
    """A host without `sandbox` in it is not a sandbox, whatever it is called.

    This is the body-level check (callbacks written into an order). The transport-level
    check is `require_api_endpoint`, which is stricter: containment in a name is not
    identity, and `sandbox.attacker.invalid` contains "sandbox".
    """
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not host:
        raise SandboxError(SANDBOX_HOST_REFUSED, "no host in %r" % (url,))
    if "sandbox" not in host:
        raise SandboxError(SANDBOX_HOST_REFUSED, host)
    return url


def require_api_endpoint(url):
    """Every request this module sends passes through here: https, and this exact host.

    Two earlier accepts were measured by the auditor and both were real: a `https://
    sandbox.attacker.invalid` passed because the word "sandbox" was in the host, and a
    plain `http://` URL passed because only the host was ever looked at. A name that
    merely contains the right word is not the right machine, and a port that speaks the
    protocol in the clear is not an API endpoint however correct its path.
    """
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or host != API_HOST:
        raise SandboxError(SANDBOX_HOST_REFUSED,
                           "%s://%s (want https://%s)" % (parts.scheme or "-", host or "-", API_HOST))
    return url


def credentials(environ=None):
    """Read the pair from the environment, at the point of use.

    Returned by value so the caller holds it for one request and no longer. Nothing here
    writes, logs, hashes-for-display or caches the secret -- a digest of a secret is still
    a secret when the secret is short, and this one is not being audited, only used.
    """
    source = os.environ if environ is None else environ
    missing = [name for name in settings.CREDENTIAL_KEYS if not source.get(name)]
    if missing:
        raise settings.MissingCredentials(missing)
    return source["PAYPAL_CLIENT_ID"], source["PAYPAL_CLIENT_SECRET"]


# ------------------------------------------------------------------------- amounts


def amount_value(amount_minor):
    """`100 -> "1.00"`. Integers only; the division is a divmod, not a float."""
    if type(amount_minor) is not int:  # bool is an int subclass and would pass `isinstance`
        raise SandboxError(AMOUNT_INVALID, "type=%s" % type(amount_minor).__name__)
    if amount_minor <= 0:
        raise SandboxError(AMOUNT_INVALID, amount_minor)
    units, cents = divmod(amount_minor, 100)
    return "%d.%02d" % (units, cents)


def parse_stamp(text):
    """The one timestamp shape the contract allows: 2026-11-03T02:17:41Z, whole seconds.

    Anything else -- a float, a local-format date, a stamp with an offset -- is not a
    timestamp this flow wrote, and a clock value nobody can place is not a clock value
    to bet money on.
    """
    if not isinstance(text, str):
        raise SandboxError(EVALUATION_TIMESTAMP_INVALID, type(text).__name__)
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise SandboxError(EVALUATION_TIMESTAMP_INVALID, text) from None


def evaluation_age_seconds(as_of, now=None):
    """Whole seconds between the evaluation's `as_of` and the real wall clock.

    Floored, not truncated: `int()` folds a stamp 0.9 seconds into the future into an
    age of 0 and accepts it, and the future is refused on the sign before any rounding.
    The floor division is deliberate -- `math.floor` without adding a name to the closed
    import set the offline test holds to.
    """
    reference = now or datetime.datetime.utcnow()
    return int((reference - parse_stamp(as_of)).total_seconds() // 1)


def check_evaluation_freshness(as_of, now=None):
    """The 300-second freshness contract, with the future refused outright.

    Two refusals, both named, because the auditor measured both holes: an evaluation
    602 seconds old passed (the bound was a day), and an evaluation dated an hour into
    the future passed too -- a clock that has not reached its own `as_of` yet has nothing
    to vouch for, and accepting it means a document can be minted "fresh" by pointing it
    at tomorrow. Past the bound the answer is a real re-evaluation, never a stretched
    timestamp.
    """
    age = evaluation_age_seconds(as_of, now)
    if age < 0:
        raise SandboxError(H56_EVALUATION_FUTURE,
                           "as_of=%s is %ds ahead of the clock" % (as_of, -age))
    if age > MAX_EVALUATION_AGE_SECONDS:
        raise SandboxError(H56_EVALUATION_STALE,
                           "as_of=%s age=%ds limit=%ds" % (as_of, age, MAX_EVALUATION_AGE_SECONDS))
    return age


def check_proposal_window(confirmed_at, now=None):
    """The 900-second business-proposal window, measured from its confirmation.

    A re-evaluation past the freshness bound may still carry the same operation forward,
    because what is being bought has not changed; what it may not do is outlive the
    proposal it was confirming. Past this window the proposal must be confirmed again --
    a new operation, a new confirmation -- and nothing is created or captured on the old
    one's momentum.
    """
    age = evaluation_age_seconds(confirmed_at, now)
    if age < 0:
        raise SandboxError(RUN_STATE_UNKNOWN,
                           "confirmed_at=%s is in the future" % (confirmed_at,))
    if age > PROPOSAL_WINDOW_SECONDS:
        raise SandboxError(PROPOSAL_EXPIRED,
                           "confirmed_at=%s age=%ds limit=%ds"
                           % (confirmed_at, age, PROPOSAL_WINDOW_SECONDS))
    return age


def operation_key(prefix, seed):
    """`PayPal-Request-Id` for any operation, derived from that operation's digest.

    Derived, not generated: a retry has to present the same key as the attempt it is
    retrying, so a random value or a timestamp would make "retry" indistinguishable from
    "second charge". The seed is the digest of everything that identifies the operation,
    so the same operation recomputes the same key from its inputs alone.
    """
    if not isinstance(seed, str) or len(seed) != 64:
        raise SandboxError(KEY_SEED_INVALID, "need a 64-char digest, got %r" % (type(seed).__name__,))
    if any(character not in "0123456789abcdef" for character in seed.lower()):
        raise SandboxError(KEY_SEED_INVALID, "not hexadecimal")
    if prefix not in ("capture", "create"):
        raise SandboxError(KEY_SEED_INVALID, "unknown operation %r" % (prefix,))
    return "h56-%s-" % prefix + seed[:32]


def commit_key(seed):
    """The `PayPal-Request-Id` for a capture."""
    return operation_key("capture", seed)


def create_key(seed):
    """The `PayPal-Request-Id` for an order creation."""
    return operation_key("create", seed)


def commit_seed(order_id, amount_minor, currency):
    """The digest a capture key is derived from: this order, this amount, this currency.

    Any retry of the same capture recomputes the same seed without consulting anything
    stored, so "same key" is a property of the inputs rather than of a saved file that
    might have been edited or lost between attempts.
    """
    amount_value(amount_minor)  # refuses non-integer and non-positive before digesting
    material = {"order_id": str(order_id), "amount_minor": amount_minor,
                "currency": str(currency)}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def create_seed(order, payee_email, operation_id):
    """The digest a create key is derived from.

    The capture key has an order id to hold on to; a creation does not, since the order id
    is what the call is trying to obtain. What identifies a creation is the business
    operation it belongs to -- and the auditor measured why the offer's attributes alone
    are not that: two separate purchases of the same item, at the same price, to the same
    payee, came out with the same key, so PayPal would have read the second purchase as a
    retry of the first. The persisted operation id is part of the key's identity, which
    keeps the two cases apart: the same operation retried recomputes the same key, and a
    different operation -- however similar its shopping basket -- derives a different one.
    The payee enters as a digest: the key travels in a request header, and a header is not
    a place an address should be readable.
    """
    if not isinstance(order, dict):
        raise SandboxError(AMOUNT_INVALID, "order is not a mapping")
    if not isinstance(operation_id, str) or not operation_id:
        raise SandboxError(OPERATION_ID_INVALID, type(operation_id).__name__)
    amount_value(order.get("amount_minor"))
    material = {"intent": "create", "operation": operation_id,
                "offer_id": str(order.get("offer_id")),
                "amount_minor": order.get("amount_minor"),
                "currency": str(order.get("currency")),
                "payee": _digest(payee_email)}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _callback(url, name):
    """Callbacks must be https and must not point at a production PayPal host."""
    parsed = urllib.parse.urlsplit(url or "")
    if parsed.scheme != "https" or not parsed.hostname:
        raise SandboxError(CALLBACK_INVALID, "%s=%r" % (name, url))
    refuse_production_host(parsed.hostname, name)
    return url


def refuse_production_host(host, name="host"):
    lowered = host.lower()
    if lowered.endswith("paypal.com") and "sandbox" not in lowered:
        raise SandboxError(SANDBOX_HOST_REFUSED, "%s=%s" % (name, lowered))


# ------------------------------------------------------------------- request bodies


def create_body(order, payee_email, return_url, cancel_url):
    """The order as PayPal wants it, built from the order the catalogue already admitted.

    No field here comes from the caller's convenience: currency and amount are read off
    `order`, which `policy.decide` has already checked against the offer, so the request
    body cannot disagree with the local verdict without one of them having drifted.
    """
    if not isinstance(order, dict):
        raise SandboxError(AMOUNT_INVALID, "order is not a mapping")
    currency = order.get("currency")
    if not isinstance(currency, str) or len(currency) != 3:
        raise SandboxError(CAPTURE_CURRENCY_MISMATCH, "currency=%r" % (currency,))
    value = amount_value(order.get("amount_minor"))
    if not isinstance(payee_email, str) or "@" not in payee_email:
        raise SandboxError(CALLBACK_INVALID, "payee_email")

    unit = {
        "reference_id": order.get("offer_id"),
        "description": order.get("description") or order.get("offer_id"),
        "amount": {"currency_code": currency, "value": value},
        "payee": {"email_address": payee_email},
    }
    return {
        "intent": "CAPTURE",
        "purchase_units": [unit],
        "application_context": {
            "brand_name": "H56 offline qualification",
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
            "return_url": _callback(return_url, "return_url"),
            "cancel_url": _callback(cancel_url, "cancel_url"),
        },
    }


# ---------------------------------------------------------------------- responses


def _loads(raw, what):
    if not isinstance(raw, (bytes, bytearray)):
        raise SandboxError(RESPONSE_UNREADABLE, "%s: not bytes" % what)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SandboxError(RESPONSE_UNREADABLE, "%s: %d bytes" % (what, len(raw)))
    try:
        value = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise SandboxError(RESPONSE_UNREADABLE, "%s: %s" % (what, type(error).__name__)) from None
    if not isinstance(value, dict):
        raise SandboxError(RESPONSE_UNREADABLE, "%s: %s" % (what, type(value).__name__))
    return value


def parse_order(raw):
    """Project a PayPal order onto the five facts this project uses, and drop the rest.

    The email is hashed on the way through. It is the payer's address, it is not needed
    for any decision here, and keeping it would put a personal identifier into every later
    layer for no benefit.
    """
    document = _loads(raw, "order")
    unit = (document.get("purchase_units") or [{}])[0]
    amount = unit.get("amount") or {}
    approve = None
    for link in document.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "approve":
            approve = link.get("href")
            break
    payer = document.get("payer") or {}
    email = payer.get("email_address")
    unit_payee = (unit.get("payee") or {})
    payee_email = unit_payee.get("email_address")
    return {
        "order_id": document.get("id"),
        "status": (document.get("status") or "").upper() or None,
        "intent": document.get("intent"),
        "currency": amount.get("currency_code"),
        "value": amount.get("value"),
        "payee_ref": _digest(payee_email) if payee_email else None,
        "approve_url": approve,
        "payer_ref": _digest(email) if email else None,
        "create_time": document.get("create_time"),
    }


def parse_capture(raw):
    """The capture facts, including what PayPal kept, so the amount rule can be checked."""
    document = _loads(raw, "capture")
    purchase = (document.get("purchase_units") or [{}])[0]
    payments = purchase.get("payments") or {}
    captures = payments.get("captures") or []
    if not captures:
        raise SandboxError(CAPTURE_MISSING, "no capture in response")
    head = captures[0] or {}
    amount = head.get("amount") or {}
    breakdown = head.get("seller_receivable_breakdown") or {}
    fee = (breakdown.get("paypal_fee") or {})
    net = (breakdown.get("net_amount") or {})
    return {
        "order_id": document.get("id"),
        "status": (document.get("status") or "").upper() or None,
        "capture_id": head.get("id"),
        "capture_status": (head.get("status") or "").upper() or None,
        "currency": amount.get("currency_code"),
        "value": amount.get("value"),
        "fee_value": fee.get("value"),
        "fee_currency": fee.get("currency_code"),
        "net_value": net.get("value"),
        "net_currency": net.get("currency_code"),
        "create_time": head.get("create_time"),
    }


def _digest(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


def payee_ref(email):
    """The public form of the payee digest: what orders and intents carry instead of an
    address, and what `verify_order` compares the order's own payee against."""
    return _digest(email)


# -------------------------------------------------------------------- state checks


def verify_order(view, order_id, order, payee_ref):
    """Compare the order PayPal holds against the order this run decided on -- first.

    Every one of these facts was available before the capture button and none of them
    needed the capture response to learn. Checking them afterwards, as the previous
    version did for the money, means the request has already been sent by the time a
    mismatch is discovered, and the auditor measured exactly that: a wrong amount was
    reported after a capture had gone out, and a wrong payee was reported never. The
    kernel does not know who a payee is; that division of labour is by design. It is why
    this layer must make the check nobody else makes.
    """
    if not isinstance(view, dict):
        raise SandboxError(ORDER_MISMATCH, "order view is not a mapping")
    if view.get("order_id") != order_id:
        raise SandboxError(ORDER_MISMATCH,
                           "order_id: paypal=%r wanted=%r" % (view.get("order_id"), order_id))
    if view.get("currency") != order.get("currency"):
        raise SandboxError(ORDER_MISMATCH,
                           "currency: paypal=%r wanted=%r" % (view.get("currency"), order.get("currency")))
    if view.get("value") != amount_value(order.get("amount_minor")):
        raise SandboxError(ORDER_MISMATCH,
                           "amount: paypal=%r wanted=%r" % (view.get("value"),
                                                            amount_value(order.get("amount_minor"))))
    if not payee_ref or view.get("payee_ref") != payee_ref:
        # Absent counts as mismatched: a payee PayPal does not name is a payee nobody
        # here can vouch for, and "probably the merchant" is not a verification.
        raise SandboxError(ORDER_MISMATCH,
                           "payee: paypal=%s wanted=%s"
                           % (view.get("payee_ref") or "ABSENT", payee_ref or "ABSENT"))
    return True


def capture_preconditions(view, decision=None):
    """Decide whether capture may proceed, from the PayPal order state alone.

    `decision` is accepted so the record can show both facts side by side, and it is
    deliberately not consulted. Passing it in and ignoring it would be a smell if this
    were a general-purpose function; here the whole point is that the governance verdict
    has no standing in this question, so the parameter is stored, not read. The command
    layer is what makes the four legs a conjunction: policy, verdict, binding and this
    approval all have to hold, and no one of them stands in for another.
    """
    status = (view or {}).get("status")
    if status == COMPLETED:
        return ALREADY_CAPTURED
    if status != APPROVED:
        raise SandboxError(PAYER_NOT_APPROVED,
                           "paypal=%s h56=%s" % (status or "NONE", decision or "NONE"))
    return CAPTURE_READY


def verify_capture(captured, expected_minor, expected_currency):
    """Compare what was captured with what the catalogue admitted. Strings, not numbers.

    The capture status is returned, not swallowed: `COMPLETED` and `PENDING` are both
    acceptable answers from PayPal and they are not the same answer. One means the money
    moved; the other means PayPal has accepted the request and said nothing yet about
    money. The caller prints different words for them and exits differently, because a
    pending capture counted as a completed one is a payment accepted that never happened.
    """
    want = amount_value(expected_minor)
    if captured.get("value") != want:
        raise SandboxError(CAPTURE_AMOUNT_MISMATCH,
                           "captured=%r wanted=%r" % (captured.get("value"), want))
    if captured.get("currency") != expected_currency:
        raise SandboxError(CAPTURE_CURRENCY_MISMATCH,
                           "captured=%r wanted=%r" % (captured.get("currency"), expected_currency))
    if captured.get("capture_status") not in (COMPLETED, "PENDING"):
        raise SandboxError(ORDER_STATE_UNEXPECTED,
                           "capture_status=%r" % (captured.get("capture_status"),))
    return captured.get("capture_status")


# ---------------------------------------------------------------------- transport


class Transport:
    """The seam. Counts calls so "no request was made" is a measurement, not a promise."""

    def __init__(self):
        self.calls = []
        self.headers_log = []

    def post(self, url, body, headers):
        raise NotImplementedError

    def get(self, url, headers):
        raise NotImplementedError

    def record(self, method, url, headers=None):
        self.calls.append((method, url))
        self.headers_log.append(dict(headers or {}))
        return len(self.calls)


def encode_request(body, headers):
    """Encode a POST body the way it will actually go on the wire.

    The caller's Content-Type decides the encoding, and the caller's Content-Type is
    never overwritten. The token endpoint was previously sent as JSON with a form header
    pasted over it -- a request PayPal documents as form-encoded, carrying a JSON body
    that the documented parser has no reason to read. Nothing about that failure is
    visible to a mock that only replays responses, which is why the bytes are built here,
    in one place, where a test can hold them.
    """
    all_headers = dict(headers)
    content_type = all_headers.get("Content-Type")
    if content_type and content_type not in (FORM_TYPE, JSON_TYPE):
        raise SandboxError(TRANSPORT_REFUSED, "content type %r is not one this module speaks" % content_type)
    if content_type == FORM_TYPE:
        if not isinstance(body, dict):
            raise SandboxError(TRANSPORT_REFUSED, "a form body must be a mapping")
        payload = urllib.parse.urlencode(body).encode("ascii")
    else:
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if not content_type:
            all_headers["Content-Type"] = JSON_TYPE
    return payload, all_headers


class MockTransport(Transport):
    """Replays canned responses. Not a stub: it enforces the endpoint rule like the live one."""

    def __init__(self, routes=None):
        Transport.__init__(self)
        self.routes = dict(routes or {})
        self.bodies = []

    def _answer(self, method, url, body=None, headers=None):
        require_api_endpoint(url)
        self.record(method, url, headers)
        if body is not None:
            self.bodies.append(body)
        key = (method, urllib.parse.urlsplit(url).path)
        if key not in self.routes:
            return 599, b'{"error":"NO_ROUTE","path":"%s"}' % key[1].encode("utf-8")
        status, payload = self.routes[key]
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        return status, payload

    def post(self, url, body, headers):
        return self._answer("POST", url, body, headers)

    def get(self, url, headers):
        return self._answer("GET", url, None, headers)


class SpyTransport(Transport):
    """Records the exact payload bytes and headers, then answers from `routes`.

    The mock above answers from routes but keeps the body as the caller handed it over;
    this one sits where `LiveTransport` sits and sees what the wire would see. The
    auditor's interception found a JSON token body under a form header; the only test
    that can catch that shape is one that reads the encoded bytes, so the bytes are what
    this transport records.
    """

    def __init__(self, routes=None):
        Transport.__init__(self)
        self.routes = dict(routes or {})
        self.sent = []

    def _answer(self, method, url, payload, headers):
        require_api_endpoint(url)
        self.record(method, url, headers)
        self.sent.append((method, url, payload, dict(headers or {})))
        key = (method, urllib.parse.urlsplit(url).path)
        if key not in self.routes:
            return 599, b"{}"
        status, body = self.routes[key]
        return status, body.encode("utf-8") if isinstance(body, str) else body

    def post(self, url, body, headers):
        payload, all_headers = encode_request(body, headers)
        return self._answer("POST", url, payload, all_headers)

    def get(self, url, headers):
        return self._answer("GET", url, None, headers)


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    """Every redirect is refused before a second request exists.

    urllib's default handler follows the jump and rebuilds the request with the caller's
    headers still attached -- Authorization included -- so a 302 off the pinned host would
    leave with credentials on it, and `_send`'s endpoint check never sees the URL being
    jumped to because it runs once, on the URL the caller asked for. The auditor measured
    exactly this in a fully in-memory 302 simulation: the second request went to another
    origin with the Authorization header still set. Refusing inside `redirect_request`
    means the decline happens before any second request is built or sent; nothing reaches
    the redirect target. The three endpoints this client speaks to never legitimately
    redirect, so a redirect at all is a signal something is wrong, whatever its target.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SandboxError(REDIRECT_REFUSED, str(newurl))


class LiveTransport(Transport):
    """Real HTTP, and only to the one pinned sandbox API host.

    Constructing it with any other host refuses immediately, and every request is
    re-checked against the pinned host before it is sent -- `self.base` is a value, and
    values can be held wrong by a caller; the endpoint check is the thing that runs. The
    opener carries `_RedirectGuard`, so a redirect cannot leave this host with the
    caller's credentials attached.
    """

    def __init__(self, base, timeout=REQUEST_TIMEOUT):
        Transport.__init__(self)
        if base != SANDBOX_BASE:
            raise SandboxError(SANDBOX_HOST_REFUSED,
                               "%s (want %s)" % (base, SANDBOX_BASE))
        self.base = base
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_RedirectGuard())

    def _send(self, method, url, payload, headers):
        require_api_endpoint(url)
        self.record(method, url, headers)
        request = urllib.request.Request(url, data=payload, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with self._opener.open(request, timeout=self.timeout) as answer:
                return answer.getcode(), answer.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            return error.code, error.read(MAX_RESPONSE_BYTES)
        except (urllib.error.URLError, socket.timeout, OSError) as error:
            raise SandboxError(TRANSPORT_REFUSED,
                               "%s: %s" % (type(error).__name__, str(error)[:80])) from None

    def post(self, url, body, headers):
        payload, all_headers = encode_request(body, headers)
        return self._send("POST", url, payload, all_headers)

    def get(self, url, headers):
        return self._send("GET", url, None, headers)


# ------------------------------------------------------------------------- client


class SandboxClient:
    """Three calls, one token, and a refusal on anything that is not the sandbox."""

    def __init__(self, transport, base=None):
        self.base = refuse_production(base or base_url())
        self.transport = transport
        self._token = None
        self._realm = None

    # -- token -------------------------------------------------------------------
    def token(self):
        if self._token:
            return self._token
        client_id, client_secret = credentials()
        pair = "%s:%s" % (client_id, client_secret)
        encoded = base64.b64encode(pair.encode("utf-8")).decode("ascii")
        status, raw = self.transport.post(
            self.base + TOKEN_PATH, {"grant_type": "client_credentials"},
            {"Authorization": "Basic " + encoded,
             "Content-Type": "application/x-www-form-urlencoded"})
        if status != 200:
            raise SandboxError(RESPONSE_REFUSED, "token: HTTP %d" % status)
        document = _loads(raw, "token")
        value = document.get("access_token")
        if not isinstance(value, str) or not value:
            raise SandboxError(RESPONSE_UNREADABLE, "token: no access_token")
        self._token = value
        self._realm = {
            "expires_in": document.get("expires_in"),
            "app_id_ref": _digest(document.get("app_id")) if document.get("app_id") else None,
            "scopes": sorted((document.get("scope") or "").split()),
        }
        return self._token

    def realm(self):
        """Public metadata about the credential, with the app id reduced to a reference."""
        if self._realm is None:
            self.token()
        return dict(self._realm)

    # -- calls -------------------------------------------------------------------
    def _headers(self, extra=None):
        headers = {"Authorization": "Bearer " + self.token()}
        headers.update(extra or {})
        return headers

    def create_order(self, order, payee_email, return_url, cancel_url, request_id=None):
        """Place the order. `request_id` makes a retry the same request, not a new one."""
        body = create_body(order, payee_email, return_url, cancel_url)
        headers = self._headers()
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        status, raw = self.transport.post(self.base + ORDERS_PATH, body, headers)
        if status not in (200, 201):
            raise SandboxError(RESPONSE_REFUSED, "create: HTTP %d" % status)
        view = parse_order(raw)
        if view["status"] != CREATED:
            raise SandboxError(ORDER_STATE_UNEXPECTED, "create returned %s" % view["status"])
        return view

    def read_order(self, order_id):
        url = self.base + ORDERS_PATH + "/" + urllib.parse.quote(str(order_id), safe="")
        status, raw = self.transport.get(url, self._headers())
        if status != 200:
            raise SandboxError(RESPONSE_REFUSED, "read: HTTP %d" % status)
        return parse_order(raw)

    def capture_order(self, order_id, seed, expected_minor, expected_currency):
        """Capture, then check the money against the catalogue rather than trusting it."""
        key = commit_key(seed)
        url = self.base + ORDERS_PATH + "/" + urllib.parse.quote(str(order_id), safe="") + "/capture"
        status, raw = self.transport.post(url, {}, self._headers({"PayPal-Request-Id": key}))
        if status not in (200, 201):
            raise SandboxError(RESPONSE_REFUSED, "capture: HTTP %d" % status)
        captured = parse_capture(raw)
        verify_capture(captured, expected_minor, expected_currency)
        return captured


# ------------------------------------------------------------------------- redaction


SENSITIVE_KEYS = ("access_token", "client_secret", "client_id", "app_id", "payer_id",
                  "email_address", "Authorization", "authorization")
REDACTED = "<redacted>"


def redact(value, ledger=None):
    """Replace sensitive values by shape, and record what was replaced without the value.

    Two different replacements, because they answer different questions. A token or a
    secret is replaced wholesale and only its length is kept -- a truncated secret is
    still a secret when the rest is guessable. An email is replaced by a digest, because
    the auditor may legitimately need to know that two records mention the same address.
    """
    if ledger is None:
        ledger = {}
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in SENSITIVE_KEYS and isinstance(item, str) and item:
                if key.lower() == "authorization":
                    # Keep the scheme, drop everything after it: "Bearer <token>" becomes
                    # "Bearer <redacted>", so the reader still knows an authorization header
                    # was present and which kind it was.
                    scheme, _, remainder = item.partition(" ")
                    marker = (scheme + " " if remainder else "") + REDACTED
                elif key in ("email_address", "payer_id", "app_id", "client_id"):
                    marker = "<ref:%s>" % _digest(item)
                else:
                    marker = "<redacted %d chars>" % len(item)
                ledger[key] = ledger.get(key, 0) + 1
                out[key] = marker
            else:
                out[key] = redact(item, ledger)
        return out
    if isinstance(value, list):
        return [redact(item, ledger) for item in value]
    if isinstance(value, str) and ("Bearer " in value):
        ledger["bearer"] = ledger.get("bearer", 0) + 1
        return "Bearer " + REDACTED
    return value


def dumps(document):
    """Canonical text for evidence files: sorted, compact, ASCII-safe."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(raw):
    """What gets written instead of the response bytes."""
    if not isinstance(raw, (bytes, bytearray)):
        raw = dumps(raw).encode("utf-8")
    return {"sha256": hashlib.sha256(bytes(raw)).hexdigest(), "bytes": len(raw)}
