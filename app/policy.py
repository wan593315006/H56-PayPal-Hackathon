"""Business policy: three independent rules that decide whether an order may be attempted.

This layer answers "may we try to pay for this?" and nothing else. It is not the kernel:
the kernel answers "is the host evidence sufficient to decide?", a different question. A
`BLOCKED` here means the kernel is never asked, and that must stay visible in the run
result instead of being reported as a kernel verdict.

No third-party imports, no kernel imports, no environment reads: the only inputs are the
catalogue and the order.
"""
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).absolute().parent.parent / "fixtures" / "catalog.json"

# The rule set is a constant, not a literal buried in the return value: the binding record
# stores it, and a binding that names the rules it was checked under catches a policy layer
# that changed shape between the run and the audit.
RULES = ("R1_AMOUNT", "R2_OFFER", "R3_PAYEE", "R4_CATALOGUE_PRICE")


class PolicyError(RuntimeError):
    def __init__(self, code, detail=""):
        self.code = code
        super().__init__(code + (": " + str(detail) if detail else ""))


def _reject_float(value):
    # The kernel refuses floats on principle; the catalogue is held to the same rule so a
    # decimal amount cannot enter the chain here and explode later at a digest boundary.
    raise PolicyError("CATALOG_AMOUNT_MUST_BE_INTEGER", value)


def _amount(value, where):
    if type(value) is not int or value <= 0:
        raise PolicyError("CATALOG_AMOUNT_INVALID", where)
    return value


def load_catalog(path=None):
    """Load and validate the catalogue. Money is integer minor units, always."""
    path = Path(path) if path is not None else CATALOG_PATH
    document = json.loads(path.read_text(encoding="utf-8"), parse_float=_reject_float)
    if document.get("schema") != "H56_PAYPAL_CATALOG_V1":
        raise PolicyError("CATALOG_SCHEMA_UNKNOWN", document.get("schema"))
    limit = _amount(document.get("per_order_limit_minor"), "per_order_limit_minor")
    payees = document.get("payees")
    if type(payees) is not list or not payees or not all(type(p) is str and p for p in payees):
        raise PolicyError("CATALOG_PAYEES_INVALID")
    offers = document.get("offers")
    if type(offers) is not list or not offers:
        raise PolicyError("CATALOG_OFFERS_INVALID")
    seen = set()
    for offer in offers:
        if type(offer) is not dict:
            raise PolicyError("CATALOG_OFFER_INVALID")
        for key in ("offer_id", "description", "currency", "payee"):
            if type(offer.get(key)) is not str or not offer[key]:
                raise PolicyError("CATALOG_OFFER_FIELD_INVALID", key)
        if offer["offer_id"] in seen:
            raise PolicyError("CATALOG_OFFER_DUPLICATED", offer["offer_id"])
        seen.add(offer["offer_id"])
        _amount(offer.get("amount_minor"), offer["offer_id"])
        if offer["amount_minor"] > limit:
            raise PolicyError("CATALOG_OFFER_ABOVE_LIMIT", offer["offer_id"])
        if offer["payee"] not in payees:
            raise PolicyError("CATALOG_OFFER_PAYEE_NOT_ALLOWED", offer["offer_id"])
    return document


def decide(order, catalog):
    """Four rules, each reporting its own code so a refusal can be explained.

    R1 amount: positive integer, within the per-order limit.
    R2 offer:  the identifier is in the catalogue.
    R3 payee:  the payee is on the whitelist.
    R4 price:  the amount must *equal* the catalogue price for that offer, and the
               currency must be the offer's.

    R4 is the rule that makes the catalogue the single source of price. Without it an
    order for 1 minor unit against a 5000 offer passes: every other rule is satisfied,
    the limit is not exceeded, and the currency matches. A limit is an upper bound, not
    a price, so "within budget" must never be read as "correct amount".

    The checks are an if/elif chain on purpose: one bad amount produces one code. A value
    that is both above the limit and not the catalogue price is reported as the limit
    breach, because that is the rule the operator can act on first.
    """
    reasons = []
    offer = None
    for candidate in catalog["offers"]:
        if candidate["offer_id"] == order.get("offer_id"):
            offer = candidate
            break

    amount = order.get("amount_minor")
    if type(amount) is not int or type(amount) is bool or amount <= 0:
        reasons.append("POLICY_AMOUNT_INVALID")
    elif amount > catalog["per_order_limit_minor"]:
        reasons.append("POLICY_AMOUNT_LIMIT_EXCEEDED")
    elif offer is not None and amount != offer["amount_minor"]:
        reasons.append("POLICY_AMOUNT_NOT_CATALOGUE_PRICE")
    if offer is not None and order.get("currency") != offer["currency"]:
        reasons.append("POLICY_CURRENCY_MISMATCH")

    if offer is None:
        reasons.append("POLICY_OFFER_NOT_IN_CATALOG")
    if order.get("payee") not in catalog["payees"]:
        reasons.append("POLICY_PAYEE_NOT_ALLOWED")

    return dict(decision="ALLOW" if not reasons else "BLOCKED",
                reason_codes=reasons,
                offer=offer,
                rules=RULES)
