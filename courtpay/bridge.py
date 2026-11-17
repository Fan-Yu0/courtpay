"""Translate a CourtPay case into the Internet Court v1 case shape.

Internet Court's jury contract takes a ``statement``, ``guidelines`` and two
sides of evidence, and returns ``PARTY_A`` / ``PARTY_B`` / ``UNDETERMINED``.
CourtPay's case is the same dispute with a payment attached, so the two map
one-to-one. The translation below is what a LayerZero bridge message would carry
once the Base escrow side is wired.
"""

from __future__ import annotations

from typing import Any, Dict

SCHEMA = "internet-court/case-v1"

GUIDELINES = (
    "Party A bought a deliverable from Party B and paid for it over x402. "
    "Decide only whether the delivered artifact at the evidence URL satisfies "
    "the statement of what was sold. Judge the artifact itself, not marketing "
    "language. If the artifact cannot be read or does not settle the claim, "
    "answer UNDETERMINED."
)

VERDICTS = {
    0: "PARTY_A",   # REFUND — the buyer's claim held
    1: "PARTY_B",   # NO_REFUND — the seller's delivery held
    2: "UNDETERMINED",
}


def statement_for(case: Dict[str, Any]) -> str:
    return "Seller promised: %s Buyer complaint: %s" % (case["promise"], case["complaint"])


def to_internet_court_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Return the payload an Internet Court jury (or bridge) would consume."""
    evidence_url = case.get("deliverable_url") or ""
    buyer_items = []
    if evidence_url:
        buyer_items.append({"url": evidence_url, "note": case.get("complaint", "")})
    return {
        "schema": SCHEMA,
        "statement": statement_for(case),
        "guidelines": GUIDELINES,
        "parties": {
            "party_a": case.get("buyer", ""),
            "party_b": case.get("seller", ""),
        },
        "evidence": {
            "party_a": buyer_items,
            "party_b": [],
        },
        "payment": {
            "receipt_hash": case.get("receipt_hash", ""),
            "amount_units": case.get("price_units", 0),
            "asset": case.get("asset", ""),
            "resource_url": case.get("resource_url", ""),
        },
        "verdict": VERDICTS.get(int(case.get("verdict", 2)), "UNDETERMINED"),
        "reasoning": case.get("reasoning", ""),
        "round": case.get("round", 0),
    }
