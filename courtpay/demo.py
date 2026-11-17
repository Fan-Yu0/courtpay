"""End-to-end demo: pay, verify, dispute, judge, refund."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

from eth_account import Account

from . import receipts
from .buyer import fetch_paid
from .catalog import CATALOG
from .court import Court, load_state, save_state, STATE_DIR
from .preflight import check_delivery
from .seller import Catalog, serve
from .x402 import LocalLedgerSettler, X402Error

DEFAULT_PORT = 8402
DEFAULT_DELIVERY_URL = (
    "https://raw.githubusercontent.com/Fan-Yu0/courtpay/master/demo/deliveries/latency-feed.json"
)


def _short(value: str, keep: int = 10) -> str:
    value = str(value)
    return value if len(value) <= keep * 2 + 2 else value[: keep + 2] + "…" + value[-keep:]


def _log(tag: str, message: str) -> None:
    print("[%s] %s" % (tag.ljust(8), message), flush=True)


def wallets() -> Dict[str, Account]:
    path = os.path.join(STATE_DIR, "wallets.json")
    os.makedirs(STATE_DIR, exist_ok=True)
    data = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    changed = False
    for role in ("seller", "buyer", "court"):
        if role not in data:
            account = Account.create()
            data[role] = account.key.hex()
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    return {role: Account.from_key(key if key.startswith("0x") else "0x" + key) for role, key in data.items()}


def run_demo(
    deliverable_url: Optional[str] = None,
    port: int = DEFAULT_PORT,
    fresh_contract: bool = False,
    skip_judgment: bool = False,
) -> Dict[str, Any]:
    accounts = wallets()
    seller, buyer = accounts["seller"], accounts["buyer"]

    catalog = Catalog(CATALOG)
    settler = LocalLedgerSettler(os.path.join(STATE_DIR, "ledger.json"))
    server = serve(seller, catalog, settler, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    resource_url = "http://127.0.0.1:%d/dataset/latency-feed" % port

    _log("seller", "%s · %s USDC · %s" % (CATALOG["latency-feed"]["title"], "0.25", _short(seller.address)))

    try:
        challenge_status = 402
        try:
            fetch_paid(resource_url, buyer, max_price=None, timeout=5)
        except X402Error as exc:
            if exc.reason == "expected_402":
                challenge_status = 200
        _log("buyer", "GET %s → %d Payment Required" % (resource_url, challenge_status))

        delivery = fetch_paid(resource_url, buyer, max_price=250000)
        _log("buyer", "signed EIP-3009 authorization → 200 OK · receipt %s" % _short(delivery.receipt_hash, 8))
        _log("buyer", "payment settled by %s · ref %s" % (settler.name, _short(delivery.payment_response.get("transaction", ""), 8)))

        payload = delivery.json_body()
        check = check_delivery(CATALOG["latency-feed"], payload)
        _log("buyer", "preflight: %d rows, missing %s" % (check["rows"], ", ".join(check["missing_fields"]) or "nothing"))

        public_url = deliverable_url or DEFAULT_DELIVERY_URL
        if not public_url:
            path = os.path.join(STATE_DIR, "delivery.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            public_url = "file://" + os.path.abspath(path).replace("\\", "/")
            _log("seller", "delivery mirrored to %s" % path)

        court = Court(accounts["court"].key.hex())
        state = load_state()
        if fresh_contract or not state.get("contract"):
            _log("court", "deploying CourtPayCourt to Studio Network")
            address = court.deploy(os.path.join("contracts", "courtpay_court.py"))
            _log("court", "contract %s" % address)
        else:
            court.contract = state["contract"]

        case = court.open_case(
            seller=seller.address,
            resource_url=delivery.url,
            promise=CATALOG["latency-feed"]["promise"],
            price_units=int(delivery.requirements["maxAmountRequired"]),
            asset=delivery.requirements["asset"],
            receipt_hash=delivery.receipt_hash,
        )
        _log("court", "case %s opened · receipt %s" % (case["case_id"], _short(delivery.receipt_hash, 8)))

        complaint = "Delivered 3 of 10 rows and every row is missing p99_ms and probe_checksum."
        court.dispute(case["case_id"], public_url, complaint)
        _log("court", "dispute filed by buyer · evidence %s" % public_url)

        result: Dict[str, Any] = {"case_id": case["case_id"], "delivery": payload, "check": check}
        if skip_judgment:
            _log("jury", "skipped (--skip-judgment)")
            return result

        _log("jury", "validators fetch the delivery themselves and re-run the review")
        started = time.time()
        court.judge(case["case_id"])
        verdict = court.get_case(case["case_id"])
        elapsed = int(time.time() - started)

        label = {0: "REFUND", 1: "NO REFUND", 2: "UNDETERMINED"}.get(int(verdict["verdict"]), "?")
        _log("jury", "%s · confidence %s · %ds" % (label, verdict["confidence"], elapsed))
        _log("jury", verdict["reasoning"][:220])
        _log("result", "refund %s of %s units · case %s" % (verdict["refund_units"], verdict["price_units"], case["case_id"]))

        result["verdict"] = verdict
        result["refund_units"] = verdict["refund_units"]
        return result
    finally:
        server.shutdown()
        server.server_close()
