"""x402 v1 "exact" scheme, implemented for EVM (EIP-3009 transferWithAuthorization).

This module is deliberately dependency-light: it speaks the wire format that x402
clients and facilitators use, so a seller built on it can later swap the local
settler for a hosted facilitator without touching the payment handshake.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Dict, Optional

from eth_account import Account
from eth_account.messages import encode_typed_data

X402_VERSION = 1
SCHEME = "exact"

# Base Sepolia USDC. The demo never needs funds: settlement is pluggable.
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
BASE_SEPOLIA_CHAIN_ID = 84532

TRANSFER_WITH_AUTHORIZATION = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


class X402Error(Exception):
    """Raised when a payment header cannot be accepted."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def b64encode_json(value: Any) -> str:
    return base64.b64encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).decode()


def b64decode_json(value: str) -> Any:
    return json.loads(base64.b64decode(value.encode()).decode())


def payment_requirements(
    resource: str,
    description: str,
    pay_to: str,
    amount: int,
    asset: str = BASE_SEPOLIA_USDC,
    network: str = "base-sepolia",
    mime_type: str = "application/json",
    timeout: int = 120,
) -> Dict[str, Any]:
    return {
        "scheme": SCHEME,
        "network": network,
        "maxAmountRequired": str(int(amount)),
        "resource": resource,
        "description": description,
        "mimeType": mime_type,
        "payTo": pay_to,
        "maxTimeoutSeconds": int(timeout),
        "asset": asset,
        "extra": {"name": "USDC", "version": "2"},
    }


def payment_required_body(requirements: Dict[str, Any], error: str = "X-PAYMENT header is required") -> Dict[str, Any]:
    return {"x402Version": X402_VERSION, "error": error, "accepts": [requirements]}


def typed_data(requirements: Dict[str, Any], authorization: Dict[str, Any]) -> Dict[str, Any]:
    extra = requirements.get("extra") or {}
    domain = {
        "name": extra.get("name", "USDC"),
        "version": extra.get("version", "2"),
        "chainId": BASE_SEPOLIA_CHAIN_ID,
        "verifyingContract": requirements["asset"],
    }
    message = {
        "from": authorization["from"],
        "to": authorization["to"],
        "value": int(authorization["value"]),
        "validAfter": int(authorization["validAfter"]),
        "validBefore": int(authorization["validBefore"]),
        "nonce": authorization["nonce"],
    }
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            **TRANSFER_WITH_AUTHORIZATION,
        },
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": message,
    }


def sign_payment(
    account: Account,
    requirements: Dict[str, Any],
    value: Optional[int] = None,
    ttl: int = 600,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Client side: produce the ``X-PAYMENT`` header for a 402 challenge."""
    now = int(now if now is not None else time.time())
    authorization = {
        "from": account.address,
        "to": requirements["payTo"],
        "value": str(int(value if value is not None else requirements["maxAmountRequired"])),
        "validAfter": str(max(0, now - 600)),
        "validBefore": str(now + ttl),
        "nonce": "0x" + os.urandom(32).hex(),
    }
    signed = Account.sign_typed_data(
        account.key, full_message=typed_data(requirements, authorization)
    )
    payload = {
        "x402Version": X402_VERSION,
        "scheme": requirements["scheme"],
        "network": requirements["network"],
        "payload": {
            "signature": signed.signature.hex() if hasattr(signed.signature, "hex") else str(signed.signature),
            "authorization": authorization,
        },
    }
    if not payload["payload"]["signature"].startswith("0x"):
        payload["payload"]["signature"] = "0x" + payload["payload"]["signature"]
    return payload


def encode_payment_header(payload: Dict[str, Any]) -> str:
    return b64encode_json(payload)


def decode_payment_header(header: str) -> Dict[str, Any]:
    try:
        return b64decode_json(header)
    except Exception as exc:  # noqa: BLE001
        raise X402Error("invalid_payload", "X-PAYMENT is not base64 JSON") from exc


def verify_payment(
    payload: Dict[str, Any],
    requirements: Dict[str, Any],
    used_nonces: set,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Server side: validate scheme, network, amount, window, nonce and signature."""
    now = int(now if now is not None else time.time())

    if payload.get("x402Version") != X402_VERSION:
        raise X402Error("unsupported_version", "x402Version must be 1")
    if payload.get("scheme") != requirements["scheme"]:
        raise X402Error("unsupported_scheme", "scheme must match the challenge")
    if payload.get("network") != requirements["network"]:
        raise X402Error("wrong_network", "payment network does not match the challenge")

    body = payload.get("payload") or {}
    authorization = body.get("authorization") or {}
    signature = body.get("signature") or ""

    for field in ("from", "to", "value", "validAfter", "validBefore", "nonce"):
        if field not in authorization:
            raise X402Error("malformed_authorization", "missing " + field)

    if authorization["to"].lower() != requirements["payTo"].lower():
        raise X402Error("wrong_payee", "authorization pays a different address")
    if int(authorization["value"]) < int(requirements["maxAmountRequired"]):
        raise X402Error("underpaid", "authorization value is below the price")
    if int(authorization["validBefore"]) <= now:
        raise X402Error("expired", "authorization has expired")
    if int(authorization["validAfter"]) > now:
        raise X402Error("not_yet_valid", "authorization is not valid yet")

    nonce = str(authorization["nonce"]).lower()
    if nonce in used_nonces:
        raise X402Error("nonce_already_used", "authorization nonce was already spent")

    message = encode_typed_data(full_message=typed_data(requirements, authorization))
    try:
        recovered = Account.recover_message(message, signature=signature)
    except Exception as exc:  # noqa: BLE001
        raise X402Error("invalid_signature", "authorization signature cannot be recovered") from exc

    if recovered.lower() != authorization["from"].lower():
        raise X402Error("invalid_signature", "authorization signer is not the payer")

    used_nonces.add(nonce)
    return {
        "payer": recovered,
        "authorization": authorization,
    }


def authorization_hash(authorization: Dict[str, Any], requirements: Dict[str, Any]) -> str:
    """Stable digest of one paid request, used as the payment reference."""
    canonical = json.dumps(
        {
            "authorization": authorization,
            "asset": requirements["asset"],
            "network": requirements["network"],
            "payTo": requirements["payTo"],
            "resource": requirements["resource"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return "0x" + hashlib.sha256(canonical.encode()).hexdigest()


class LocalLedgerSettler:
    """Demo settler: records the authorized transfer in a local ledger file.

    A production deployment swaps this for an x402 facilitator client (see
    ``README.md`` -> "Settlement adapters"). The authorization itself is a real
    EIP-3009 payload, so the same bytes can be broadcast on Base Sepolia.
    """

    name = "local-ledger"

    def __init__(self, path: str):
        self.path = path

    def _load(self) -> list:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def settle(self, authorization: Dict[str, Any], requirements: Dict[str, Any]) -> str:
        reference = authorization_hash(authorization, requirements)
        entries = self._load()
        entries.append(
            {
                "reference": reference,
                "resource": requirements["resource"],
                "payTo": requirements["payTo"],
                "payer": authorization["from"],
                "value": str(authorization["value"]),
                "asset": requirements["asset"],
                "network": requirements["network"],
                "settledAt": int(time.time()),
                "settler": self.name,
            }
        )
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, sort_keys=True)
        return "local:" + reference
