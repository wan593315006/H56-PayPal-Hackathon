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
import re

from . import hostproof, policy

SCHEMA = "H56_APP_BINDING_V1"

# Twelve hex characters is 48 bits inside a 64-character token budget. It is an identity
# tag, not a cryptographic commitment: the commitment is the full digest in `order_sha256`.
ORDER_TOKEN_LENGTH = 12

PROPOSAL_FIELDS = ("offer_id", "amount_minor", "currency", "payee")
ORDER_FIELDS = ("order_id",) + PROPOSAL_FIELDS + ("amount_source",)
REFERENCE_FIELDS = ("assessment_id", "decision_id", "semantic_sha256",
                    "artifact_sha256", "journal_event_sha256")
BOUNDARY_FIELDS = ("authority_granted", "execution_permitted", "business_action_calls")

# The shape `identifiers()` produces for the stamp segment of a request id: 20261103T171000Z.
# It is what makes the position of the order token checkable rather than merely present.
STAMP_SHAPE = re.compile(r"[0-9]{8}T[0-9]{6}Z")

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
ORDER_TOKEN_MISPLACED = "BINDING_ORDER_TOKEN_MISPLACED"
EVIDENCE_NOT_REQUESTED = "BINDING_EVIDENCE_NOT_REQUESTED"
REFERENCE_INCOMPLETE = "BINDING_REFERENCE_INCOMPLETE"
ASSESSMENT_FOR_DIFFERENT_REQUEST = "BINDING_ASSESSMENT_FOR_DIFFERENT_REQUEST"
ASSESSMENT_UNAVAILABLE = "BINDING_ASSESSMENT_UNAVAILABLE"
RECORD_UNAVAILABLE = "BINDING_RECORD_UNAVAILABLE"
RESULT_DECISION_MISMATCH = "BINDING_RESULT_DECISION_MISMATCH"
RESULT_ASSESSMENT_MISMATCH = "BINDING_RESULT_ASSESSMENT_MISMATCH"
RESULT_DECISION_ID_MISMATCH = "BINDING_RESULT_DECISION_ID_MISMATCH"
RESULT_SEMANTIC_MISMATCH = "BINDING_RESULT_SEMANTIC_MISMATCH"
RESULT_CALLS_MISMATCH = "BINDING_RESULT_CALLS_MISMATCH"
RESULT_BOUNDARY_MISMATCH = "BINDING_RESULT_BOUNDARY_MISMATCH"


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


def carries_order(request_id, token):
    """True only when the token ends the identifier and a stamp precedes it.

    `request_id_for` builds `req_<business>_<stamp>_<token>`. The business label is chosen
    by the caller and may contain underscores and hex digits, so the split is taken from the
    right: the last segment is the token, the segment before it is the stamp.

    This replaces a substring test, which was wrong in a way that mattered. With the
    business label set to a *new* order's token, the old assessment verified clean against
    that new order: the token was "in" the request id, just not where it means anything.
    Presence is not position.
    """
    if type(request_id) is not str or type(token) is not str or not token:
        return False
    head, separator, last = request_id.rpartition("_")
    if not separator or last != token:
        return False
    prefix, separator, stamp = head.rpartition("_")
    if not separator or STAMP_SHAPE.fullmatch(stamp) is None:
        return False
    return prefix.startswith("req_")


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

    measured_evidence = hashlib.sha256(evidence_raw).hexdigest()
    if binding.get("evidence_sha256") != measured_evidence:
        found.append(EVIDENCE_MISMATCH)
    # The request fixed a digest of the evidence at the moment it was made. If the bytes
    # handed to this check no longer hash to that value, the evidence was replaced after the
    # fact; resealing `binding.evidence_sha256` over the new bytes does not undo it. Without
    # this line the binding was self-consistent with whatever evidence it was shown.
    if request.get("raw_evidence_sha256") != measured_evidence:
        found.append(EVIDENCE_NOT_REQUESTED)

    # The two links that make an old assessment unusable for a new order.
    request_id = request.get("request_id") or ""
    token = order_token(order)
    if token not in request_id:
        found.append(ORDER_NOT_IN_REQUEST)
    elif not carries_order(request_id, token):
        found.append(ORDER_TOKEN_MISPLACED)
    reference = binding.get("reference") or {}
    if sorted(reference) != sorted(REFERENCE_FIELDS):
        found.append(REFERENCE_INCOMPLETE)
    elif reference.get("assessment_id") != "ASSESS:" + value_sha256(request):
        found.append(ASSESSMENT_FOR_DIFFERENT_REQUEST)

    return found


def check_result(result, record):
    """Compare what the run claims to have decided against what the kernel recorded.

    `check()` answers "is this binding consistent with these request and evidence bytes".
    It cannot answer "did this run actually decide that", because the answer lives in the
    record store. Fetching the record and then not comparing it is the gap this covers: a
    `result.json` whose decision was edited from INFEASIBLE to FEASIBLE used to verify
    clean, because the stored record was opened, confirmed to exist, and discarded.

    Existence is not agreement.
    """
    if not isinstance(record, dict):
        return [RECORD_UNAVAILABLE]
    found = []
    projection = record.get("c2_projection") or {}
    if result.get("decision") != projection.get("decision"):
        found.append(RESULT_DECISION_MISMATCH)
    if result.get("assessment_id") != record.get("assessment_id"):
        found.append(RESULT_ASSESSMENT_MISMATCH)
    if result.get("decision_id") != record.get("decision_id"):
        found.append(RESULT_DECISION_ID_MISMATCH)
    shown = result.get("reference") or {}
    if shown.get("semantic_sha256") != record.get("semantic_sha256"):
        found.append(RESULT_SEMANTIC_MISMATCH)
    calls = (record.get("mapping_trace") or {}).get("native_calls") or []
    if result.get("native_calls") != len(calls):
        found.append(RESULT_CALLS_MISMATCH)
    recorded_boundary = record.get("boundary") or {}
    if any(result.get(field) != recorded_boundary.get(field) for field in BOUNDARY_FIELDS):
        found.append(RESULT_BOUNDARY_MISMATCH)
    return found


def audit(binding, catalog, result, request, evidence_raw, open_record):
    """The whole check, in one place, so the CLI and the gate cannot drift apart.

    Three layers, cheapest first:

    * bytes   -- is the binding self-consistent, and does it match these exact request bytes
    * request -- does the order token sit in its own position, and do the evidence bytes
                 still hash to the digest the request fixed
    * record  -- does the displayed verdict equal the verdict the kernel recorded

    `open_record(session, reference)` returns the record the kernel stored. It is a parameter
    rather than an import because this module deliberately has no kernel dependency, so it
    still runs when the kernel cannot be loaded.

    What is *not* delegated is the decision of when to call it: skip the store only when the
    binding has no reference to look up, and turn any refusal there into `ASSESSMENT_UNAVAILABLE`.
    That rule was written out twice -- once in the CLI, once in the gate -- and two copies of a
    rule is one copy that gets edited alone. Both callers now hand in a two-line loader and
    nothing else; the sequence is the same code for both, which is what "shared" has to mean.

    Returns `(findings, record)`; `record` is None when the store was never consulted.
    """
    found = check(binding, catalog, result.get("order") or {}, request, evidence_raw)
    record = None
    if REFERENCE_INCOMPLETE not in found and SCHEMA_UNKNOWN not in found:
        try:
            record = open_record(binding.get("session"), binding.get("reference"))
        except Exception as error:  # noqa: BLE001 - any refusal here is the finding
            found.append("%s:%s" % (ASSESSMENT_UNAVAILABLE,
                                    getattr(error, "code", type(error).__name__)))
    found.extend(check_result(result, record))
    return found, record


def inconsistent(ours, theirs):
    """True when two values disagree, with a type check that `None != 0` cannot express."""
    return type(ours) is not type(theirs) or ours != theirs
