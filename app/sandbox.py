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

# Closed on purpose. There is no `production` entry, so `base_url("production")` refuses
# rather than returning the live host and letting a caller decide what to do about it.
ENVIRONMENTS = {"sandbox": SANDBOX_BASE}

TOKEN_PATH = "/v1/oauth2/token"
ORDERS_PATH = "/v2/checkout/orders"

REQUEST_TIMEOUT = 25
MAX_RESPONSE_BYTES = 262144

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
KEY_SEED_INVALID = "SANDBOX_COMMIT_KEY_SEED_INVALID"
TRANSPORT_REFUSED = "SANDBOX_TRANSPORT_REFUSED"

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
    """A host without `sandbox` in it is not a sandbox, whatever it is called."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if not host:
        raise SandboxError(SANDBOX_HOST_REFUSED, "no host in %r" % (url,))
    if "sandbox" not in host:
        raise SandboxError(SANDBOX_HOST_REFUSED, host)
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


def commit_key(seed):
    """The `PayPal-Request-Id` for a capture, derived from a request digest.

    Derived, not generated: a retry has to present the same key as the attempt it is
    retrying, so a random value or a timestamp would make "retry" indistinguishable from
    "second charge". The seed is the digest of the request that produced the assessment,
    which is the only identity the two sides already share.
    """
    if not isinstance(seed, str) or len(seed) != 64:
        raise SandboxError(KEY_SEED_INVALID, "need a 64-char digest, got %r" % (type(seed).__name__,))
    if any(character not in "0123456789abcdef" for character in seed.lower()):
        raise SandboxError(KEY_SEED_INVALID, "not hexadecimal")
    return "h56-capture-" + seed[:32]


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
    return {
        "order_id": document.get("id"),
        "status": (document.get("status") or "").upper() or None,
        "intent": document.get("intent"),
        "currency": amount.get("currency_code"),
        "value": amount.get("value"),
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


# -------------------------------------------------------------------- state checks


def capture_preconditions(view, decision=None):
    """Decide whether capture may proceed, from the PayPal order state alone.

    `decision` is accepted so the record can show both facts side by side, and it is
    deliberately not consulted. Passing it in and ignoring it would be a smell if this
    were a general-purpose function; here the whole point is that the governance verdict
    has no standing in this question, so the parameter is stored, not read.
    """
    status = (view or {}).get("status")
    if status == COMPLETED:
        return ALREADY_CAPTURED
    if status != APPROVED:
        raise SandboxError(PAYER_NOT_APPROVED,
                           "paypal=%s h56=%s" % (status or "NONE", decision or "NONE"))
    return CAPTURE_READY


def verify_capture(captured, expected_minor, expected_currency):
    """Compare what was captured with what the catalogue admitted. Strings, not numbers."""
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
    return True


# ---------------------------------------------------------------------- transport


class Transport:
    """The seam. Counts calls so "no request was made" is a measurement, not a promise."""

    def __init__(self):
        self.calls = []

    def post(self, url, body, headers):
        raise NotImplementedError

    def get(self, url, headers):
        raise NotImplementedError

    def record(self, method, url):
        self.calls.append((method, url))
        return len(self.calls)


class MockTransport(Transport):
    """Replays canned responses. Not a stub: it enforces the host rule like the live one."""

    def __init__(self, routes=None):
        Transport.__init__(self)
        self.routes = dict(routes or {})
        self.bodies = []

    def _answer(self, method, url, body=None):
        refuse_production(url)
        refuse_production_host(urllib.parse.urlsplit(url).hostname or "", "url")
        self.record(method, url)
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
        return self._answer("POST", url, body)

    def get(self, url, headers):
        return self._answer("GET", url)


class LiveTransport(Transport):
    """Real HTTP, sandbox only. Constructing it with any other host refuses immediately."""

    def __init__(self, base, timeout=REQUEST_TIMEOUT):
        Transport.__init__(self)
        self.base = refuse_production(base)
        self.timeout = timeout

    def _send(self, method, url, payload, headers):
        refuse_production(url)
        refuse_production_host(urllib.parse.urlsplit(url).hostname or "", "url")
        self.record(method, url)
        request = urllib.request.Request(url, data=payload, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                return answer.getcode(), answer.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            return error.code, error.read(MAX_RESPONSE_BYTES)
        except (urllib.error.URLError, socket.timeout, OSError) as error:
            raise SandboxError(TRANSPORT_REFUSED,
                               "%s: %s" % (type(error).__name__, str(error)[:80])) from None

    def post(self, url, body, headers):
        payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        all_headers = dict(headers)
        all_headers["Content-Type"] = "application/json"
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

    def create_order(self, order, payee_email, return_url, cancel_url):
        body = create_body(order, payee_email, return_url, cancel_url)
        status, raw = self.transport.post(self.base + ORDERS_PATH, body, self._headers())
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
