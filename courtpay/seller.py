"""x402-protected seller: paid dataset endpoints with signed receipts."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from eth_account import Account

from . import receipts
from .x402 import (
    BASE_SEPOLIA_USDC,
    X402Error,
    decode_payment_header,
    encode_payment_header,
    payment_required_body,
    payment_requirements,
    verify_payment,
)


class Catalog:
    def __init__(self, entries: Dict[str, Dict[str, Any]]):
        self.entries = entries

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self.entries.get(key)

    def public_view(self) -> Dict[str, Any]:
        return {
            key: {
                "title": entry["title"],
                "promise": entry["promise"],
                "priceUnits": entry["price_units"],
                "asset": entry.get("asset", "USDC"),
            }
            for key, entry in self.entries.items()
        }


def build_handler(account: Account, catalog: Catalog, settler, used_nonces: set):
    class Handler(BaseHTTPRequestHandler):
        server_version = "courtpay-seller/1.0"

        def log_message(self, fmt: str, *args):  # quiet by default
            if getattr(self.server, "verbose", False):
                super().log_message(fmt, *args)

        def _send(self, status: int, body: bytes, headers: Optional[Dict[str, str]] = None, ctype="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
            self._send(status, json.dumps(payload, indent=2).encode(), headers)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            base = "http://" + self.headers.get("Host", "127.0.0.1")

            if parsed.path in ("/", "/catalog"):
                self._json(200, {"seller": account.address, "items": catalog.public_view()})
                return

            if not parsed.path.startswith("/dataset/"):
                self._json(404, {"error": "not_found"})
                return

            key = parsed.path[len("/dataset/"):].strip("/")
            entry = catalog.get(key)
            if entry is None:
                self._json(404, {"error": "unknown_dataset", "id": key})
                return

            resource = base + parsed.path
            requirements = payment_requirements(
                resource=resource,
                description=entry["title"],
                pay_to=account.address,
                amount=entry["price_units"],
                asset=entry.get("asset", None) or BASE_SEPOLIA_USDC,
            )

            header = self.headers.get("X-PAYMENT")
            if not header:
                self._json(402, payment_required_body(requirements), {"WWW-Authenticate": "x402"})
                return

            try:
                payload = decode_payment_header(header)
                verified = verify_payment(payload, requirements, used_nonces)
            except X402Error as exc:
                body = payment_required_body(requirements, error=exc.reason)
                self._json(402, body)
                return

            reference = settler.settle(verified["authorization"], requirements)
            delivery = json.dumps(entry["delivery"], indent=2).encode()
            receipt = receipts.sign_receipt(
                account,
                receipts.build_receipt(
                    resource=resource,
                    promise=entry["promise"],
                    buyer=verified["payer"],
                    seller=account.address,
                    pay_to=account.address,
                    amount=verified["authorization"]["value"],
                    asset=requirements["asset"],
                    network=requirements["network"],
                    payment_ref=reference,
                    delivery=delivery,
                    issued_at=int(time.time()),
                ),
            )
            headers = {
                "X-PAYMENT-RESPONSE": encode_payment_header(
                    {"success": True, "transaction": reference, "network": requirements["network"]}
                ),
                "X-COURTPAY-RECEIPT": encode_payment_header(receipt),
            }
            self._send(200, delivery, headers)

    return Handler


def serve(account: Account, catalog: Catalog, settler, host: str = "127.0.0.1", port: int = 8402, verbose: bool = False):
    used_nonces: set = set()
    handler = build_handler(account, catalog, settler, used_nonces)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.verbose = verbose
    return httpd
