"""Signed delivery receipts.

A receipt is the seller's signed statement of what was sold and what was
delivered. The buyer keeps it, and its hash is the on-chain case identifier that
ties a GenLayer dispute to one x402 payment.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from eth_account import Account
from eth_account.messages import encode_defunct

SCHEMA = "courtpay/receipt-v1"


def canonical(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def digest(value: Any) -> str:
    return "0x" + hashlib.sha256(canonical(value).encode()).hexdigest()


def build_receipt(
    *,
    resource: str,
    promise: str,
    buyer: str,
    seller: str,
    pay_to: str,
    amount: str,
    asset: str,
    network: str,
    payment_ref: str,
    delivery: bytes,
    issued_at: int,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "resource": resource,
        "promise": promise,
        "buyer": buyer,
        "seller": seller,
        "payTo": pay_to,
        "amount": str(amount),
        "asset": asset,
        "network": network,
        "paymentRef": payment_ref,
        "deliveryHash": "0x" + hashlib.sha256(delivery).hexdigest(),
        "deliveryBytes": len(delivery),
        "issuedAt": int(issued_at),
    }


def sign_receipt(account: Account, payload: Dict[str, Any]) -> Dict[str, Any]:
    signed = Account.sign_message(encode_defunct(text=canonical(payload)), private_key=account.key)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    return {"payload": payload, "signature": signature, "signer": account.address}


def verify_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    payload = receipt.get("payload") or {}
    signature = receipt.get("signature") or ""
    signer = Account.recover_message(encode_defunct(text=canonical(payload)), signature=signature)
    if signer.lower() != str(payload.get("seller", "")).lower():
        raise ValueError("receipt is not signed by the stated seller")
    return payload


def receipt_hash(receipt: Dict[str, Any]) -> str:
    return digest(receipt)[2:]
