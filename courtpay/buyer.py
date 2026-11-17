"""Buyer agent: pay an x402 endpoint and keep the signed receipt."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from eth_account import Account

from . import receipts
from .x402 import X402Error, decode_payment_header, encode_payment_header, sign_payment


@dataclass
class PaidDelivery:
    url: str
    status: int
    body: bytes
    requirements: Dict[str, Any]
    receipt: Dict[str, Any]
    receipt_hash: str
    payment_response: Dict[str, Any]

    def json_body(self) -> Any:
        return json.loads(self.body.decode())


def _request(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def fetch_paid(url: str, account: Account, max_price: Optional[int] = None, timeout: int = 30) -> PaidDelivery:
    status, _headers, body = _request(url, timeout=timeout)
    if status != 402:
        raise X402Error("expected_402", "endpoint did not demand payment (status %s)" % status)

    challenge = json.loads(body.decode())
    if challenge.get("x402Version") != 1 or not challenge.get("accepts"):
        raise X402Error("invalid_challenge", "402 body is not an x402 v1 challenge")
    requirements = challenge["accepts"][0]

    price = int(requirements["maxAmountRequired"])
    if max_price is not None and price > int(max_price):
        raise X402Error("over_budget", "asking price %s exceeds the buyer budget %s" % (price, max_price))

    payload = sign_payment(account, requirements)
    status, headers, body = _request(
        url,
        headers={"X-PAYMENT": encode_payment_header(payload)},
        timeout=timeout,
    )
    if status != 200:
        raise X402Error("payment_rejected", "seller answered %s: %s" % (status, body[:200]))

    receipt_header = headers.get("X-COURTPAY-RECEIPT") or headers.get("x-courtpay-receipt")
    if not receipt_header:
        raise X402Error("missing_receipt", "paid response carried no signed receipt")
    receipt = decode_payment_header(receipt_header)
    payload_checked = receipts.verify_receipt(receipt)

    response_header = headers.get("X-PAYMENT-RESPONSE") or headers.get("x-payment-response")
    payment_response = decode_payment_header(response_header) if response_header else {}

    return PaidDelivery(
        url=url,
        status=status,
        body=body,
        requirements=requirements,
        receipt=receipt,
        receipt_hash=receipts.receipt_hash(receipt),
        payment_response=payment_response,
    )
