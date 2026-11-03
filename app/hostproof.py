"""Build the host-evidence envelope handed to the kernel: nine keys, seven-key items.

The envelope is a *claim about the current moment*, so the timestamps are taken from the
clock at build time and never from a fixture file. A fixture timestamp from 2026-10-24 is
the single most expensive mistake available here: it is not rejected, it silently ages
past the 300-second window, every field built on it is voided, and the kernel answers
`DEFER`. That looks exactly like a wrong verdict and sends you hunting in the kernel for a
bug that lives in this file.

Two habits are enforced by the shape of the API rather than by a comment:

* `as_of` is passed in, `observed_at` defaults to it — the envelope and the request cannot
  drift apart because one clock reading feeds both;
* serialisation is deterministic and reusable, so `raw_evidence_sha256` is computed over
  the bytes that actually land on disk, never over a dict.

No third-party imports, no kernel imports, no clock reads outside `utc_now()`.
"""
import datetime
import json

SCHEMA = "H56_ENV_EVIDENCE_V1"
GRADE = "SYNTHETIC_ONLY"
SOURCE_ID = "SYNTHETIC_FIXTURE_V1"
SOURCE_VERSION = "1.0.0"
ROLE = "SIMULATED_OPERATOR_METADATA_HOST"

ENVELOPE_KEYS = ("schema", "evidence_set_id", "evidence_grade", "source_id",
                 "source_version", "environment_id", "environment_role", "task_ref", "items")
ITEM_KEYS = ("evidence_id", "field", "knowledge", "value", "source_id",
             "observed_at", "coverage")

FIELDS = ("app_container", "integrity_rid", "outer_job_clear",
          "host_directory_normal", "dependencies_available", "supporting_attestation")

# The passing baseline. `outer_job_clear` is the only field whose coverage is part of the
# contract: FIELD_ONLY there is refused as ENV_OUTER_JOB_SCOPE_INCOMPLETE even though the
# value itself is true.
BASELINE = (
    ("app_container", False, "FIELD_ONLY"),
    ("integrity_rid", 12288, "FIELD_ONLY"),
    ("outer_job_clear", True, "FULL_ANCESTOR_CHAIN"),
    ("host_directory_normal", True, "FIELD_ONLY"),
    ("dependencies_available", True, "FIELD_ONLY"),
    ("supporting_attestation", True, "FIELD_ONLY"),
)
REQUIRED_COVERAGE = {"outer_job_clear": "FULL_ANCESTOR_CHAIN"}
STAMP = "%Y-%m-%dT%H:%M:%SZ"


class HostProofError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def utc_now():
    """One clock reading, second precision, UTC. The only clock read in this package."""
    return datetime.datetime.utcnow()


def stamp(moment):
    return moment.strftime(STAMP)


def shift(moment, seconds):
    """Move a moment by whole seconds, used to build an expired snapshot on purpose."""
    return moment + datetime.timedelta(seconds=seconds)


def dumps(value):
    """Deterministic serialisation; must equal the kernel's `canonical()` byte for byte.

    h56bridge asserts that equality once per run, so a drift between the two shows up as a
    named failure rather than as a digest that quietly stops matching.
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def encode(envelope):
    return dumps(envelope).encode("utf-8")


def items(as_of, observed_at=None, values=None, coverage=None):
    """Six items, one per field. `values`/`coverage` override the baseline for one field."""
    observed_at = observed_at or as_of
    values = dict(values or {})
    coverage = dict(coverage or {})
    built = []
    for index, (field, value, default_coverage) in enumerate(BASELINE, 1):
        if field in values:
            value = values[field]
        built.append({
            "evidence_id": "EV%d_%s" % (index, field),
            "field": field,
            "knowledge": "UNKNOWN" if value is None else "KNOWN",
            "value": value,
            "source_id": SOURCE_ID,
            "observed_at": observed_at,
            "coverage": coverage.get(field, default_coverage),
        })
    return built


def build(environment_id, task_ref, as_of, observed_at=None, values=None,
          coverage=None, extra_items=(), evidence_set_id=None):
    """Return `(envelope, raw_bytes)` for one host snapshot.

    `as_of` is the request's timestamp; passing it here is what keeps the envelope's
    `environment_id` and `task_ref` identical to the request's, field for field.
    """
    if not isinstance(as_of, str):
        raise HostProofError("AS_OF_MUST_BE_STAMP", type(as_of).__name__)
    envelope = {
        "schema": SCHEMA,
        "evidence_set_id": evidence_set_id or ("ES-" + as_of.replace("-", "").replace(":", "")),
        "evidence_grade": GRADE,
        "source_id": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "environment_id": environment_id,
        "environment_role": ROLE,
        "task_ref": task_ref,
        "items": items(as_of, observed_at, values, coverage) + list(extra_items),
    }
    return envelope, encode(envelope)


def fields_text(envelope):
    """Compact summary for the console: which fields are known, and at what coverage."""
    known = [i["field"] for i in envelope["items"] if i["knowledge"] == "KNOWN"]
    return "%d/%d known: %s" % (len(known), len(FIELDS), ",".join(sorted(known)))
