"""Bind one order to exactly one kernel assessment, and refuse a later substitution.

The kernel record proves *an* assessment happened for *a* request. It says nothing about
which order that request was for. `evaluate_command` used to attach the order to the
result summary as a label, so editing the order left every kernel check passing: the
kernel verified its own record, and the order was never part of that record.

This module closes that gap from the outside, without touching the 139-file core. The
mechanism is a chain, not a checklist:

    order -> order digest -> request_id -> request -> assessment_id

The order's digest is embedded in `request_id`, and the kernel derives `assessment_id`
from the digest of the whole request. Changing the order therefore breaks the last link:
the recorded assessment id stops equalling the digest of the request that claims to carry
the new order. Re-using an old assessment for a new order is not something an operator
has to remember not to do; it cannot be made to line up.

What this does **not** do: it does not stop someone who owns the record store from
re-running the kernel and rewriting every file consistently. That would be a new
assessment with a new id, not a reused one. Detecting a genuine re-run is the journal's
job, not this file's, and saying otherwise would be the kind of overclaim this package is
supposed to avoid.

No third-party imports, no kernel imports: every value here is recomputed from the bytes
on disk plus the catalogue, so the check runs even if the kernel cannot be loaded.
"""
import hashlib

from . import hostproof, policy

SCHEMA = "H56_APP_BINDING_V1"

# Twelve hex characters is 48 bits inside a 64-character token budget. It is an identity
# tag, not a cryptographic commitment: the commitment is the full digest in `order_sha256`.
ORDER_TOKEN_LENGTH = 12

PROPOSAL_FIELDS = ("offer_id", "amount_minor", "currency", "payee")
ORDER_FIELDS = ("order_id",) + PROPOSAL_FIELDS + ("amount_source",)
REFERENCE_FIELDS = ("assessment_id", "decision_id", "semantic_sha256",
                    "artifact_sha256", "journal_event_sha256")

# Every finding is named. A binding check that returns a bare boolean tells an operator
# that something is wrong without telling them which of seven links broke.
TAMPERED = "BINDING_TAMPERED"
SCHEMA_UNKNOWN = "BINDING_SCHEMA_UNKNOWN"
CATALOGUE_DRIFT = "BINDING_CATALOGUE_DRIFT"
POLICY_DRIFT = "BINDING_POLICY_DRIFT"
ORDER_MISMATCH = "BINDING_ORDER_MISMATCH"
PROPOSAL_MISMATCH = "BINDING_PROPOSAL_MISMATCH"
REQUEST_MISMATCH = "BINDING_REQUEST_MISMATCH"
EVIDENCE_MISMATCH = "BINDING_EVIDENCE_MISMATCH"
ORDER_NOT_IN_REQUEST = "BINDING_ORDER_NOT_IN_REQUEST"
REFERENCE_INCOMPLETE = "BINDING_REFERENCE_INCOMPLETE"
ASSESSMENT_FOR_DIFFERENT_REQUEST = "BINDING_ASSESSMENT_FOR_DIFFERENT_REQUEST"
ASSESSMENT_UNAVAILABLE = "BINDING_ASSESSMENT_UNAVAILABLE"


class BindingError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def value_sha256(value):
    """The kernel's digest, reproduced without importing the kernel.

    `contracts.digest` is `sha256(canonical(value))`, and `hostproof.dumps` is asserted
    equal to `canonical` once per run by `h56bridge.check_canonical`. Re-deriving it here
    keeps this module loadable when the core is absent, which is when an audit most needs
    to read a binding.
    """
    return hashlib.sha256(hostproof.dumps(value).encode("utf-8")).hexdigest()


def order_token(order):
    return value_sha256(order)[:ORDER_TOKEN_LENGTH]


def request_id_for(base_request_id, order):
    """The request identifier carries the order's fingerprint, so the two cannot drift."""
    return "%s_%s" % (base_request_id, order_token(order))


def _seal(body):
    sealed = dict(body)
    sealed["binding_sha256"] = value_sha256(body)
    return sealed


def make(catalog, order, request, evidence_raw, reference, session):
    """Build the binding record for one completed run."""
    missing = [key for key in REFERENCE_FIELDS if key not in reference]
    if missing:
        raise BindingError(REFERENCE_INCOMPLETE, ",".join(missing))
    for key in ORDER_FIELDS:
        if key not in order:
            raise BindingError(ORDER_MISMATCH, "order is missing " + key)
    body = {
        "schema": SCHEMA,
        "proposal": {key: order[key] for key in PROPOSAL_FIELDS},
        "catalogue": {
            "schema": catalog.get("schema"),
            "per_order_limit_minor": catalog.get("per_order_limit_minor"),
            "sha256": value_sha256(catalog),
        },
        "policy": {"rules": list(policy.RULES), "decision": "ALLOW"},
        "order": dict(order),
        "order_sha256": value_sha256(order),
        "order_token": order_token(order),
        "request_id": request["request_id"],
        "request_sha256": value_sha256(request),
        "evidence_sha256": hashlib.sha256(evidence_raw).hexdigest(),
        "session": session,
        "reference": {key: reference[key] for key in REFERENCE_FIELDS},
    }
    return _seal(body)


def check(binding, catalog, order, request, evidence_raw):
    """Return every finding; an empty list means all links hold.

    Ordered from cheapest and most local to most structural, so the first code printed is
    the one an operator can act on without reading the rest.
    """
    found = []
    if binding.get("schema") != SCHEMA:
        return [SCHEMA_UNKNOWN]

    body = {key: value for key, value in binding.items() if key != "binding_sha256"}
    if binding.get("binding_sha256") != value_sha256(body):
        found.append(TAMPERED)

    if (binding.get("catalogue") or {}).get("sha256") != value_sha256(catalog):
        found.append(CATALOGUE_DRIFT)
    if list((binding.get("policy") or {}).get("rules") or []) != list(policy.RULES):
        found.append(POLICY_DRIFT)

    if binding.get("order_sha256") != value_sha256(order):
        found.append(ORDER_MISMATCH)
    proposal = binding.get("proposal") or {}
    if any(inconsistent(order.get(key), proposal.get(key)) for key in PROPOSAL_FIELDS):
        found.append(PROPOSAL_MISMATCH)

    if binding.get("request_sha256") != value_sha256(request):
        found.append(REQUEST_MISMATCH)
    if binding.get("evidence_sha256") != hashlib.sha256(evidence_raw).hexdigest():
        found.append(EVIDENCE_MISMATCH)

    # The two links that make an old assessment unusable for a new order.
    request_id = request.get("request_id") or ""
    if order_token(order) not in request_id:
        found.append(ORDER_NOT_IN_REQUEST)
    reference = binding.get("reference") or {}
    if sorted(reference) != sorted(REFERENCE_FIELDS):
        found.append(REFERENCE_INCOMPLETE)
    elif reference.get("assessment_id") != "ASSESS:" + value_sha256(request):
        found.append(ASSESSMENT_FOR_DIFFERENT_REQUEST)

    return found


def inconsistent(ours, theirs):
    """True when two values disagree, with a type check that `None != 0` cannot express."""
    return type(ours) is not type(theirs) or ours != theirs
