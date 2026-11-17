"""CourtPay command line."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import receipts
from .buyer import fetch_paid
from .catalog import CATALOG
from .court import Court
from .demo import DEFAULT_PORT, run_demo, wallets
from .seller import Catalog, serve
from .x402 import LocalLedgerSettler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="courtpay", description="x402 purchases that can go to court")
    parser.add_argument("--state-dir", default=None, help="where wallets, receipts and contract state live")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run the full pay → dispute → judgment flow")
    demo.add_argument("--deliverable-url", default=os.environ.get("COURTPAY_DELIVERABLE_URL"))
    demo.add_argument("--port", type=int, default=DEFAULT_PORT)
    demo.add_argument("--fresh", action="store_true", help="deploy a new contract instead of reusing state")
    demo.add_argument("--skip-judgment", action="store_true")

    serve_cmd = sub.add_parser("serve", help="run the x402-protected seller")
    serve_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)

    buy = sub.add_parser("buy", help="buy one paid resource and store the receipt")
    buy.add_argument("--url", required=True)
    buy.add_argument("--max-price", type=int, default=250000)
    buy.add_argument("--out", default="receipt.json")

    dispute = sub.add_parser("dispute", help="open a GenLayer case from a stored receipt")
    dispute.add_argument("--receipt", required=True)
    dispute.add_argument("--deliverable-url", required=True)
    dispute.add_argument("--complaint", required=True)
    dispute.add_argument("--contract", default=None)

    args = parser.parse_args(argv)
    if args.state_dir:
        os.environ["COURTPAY_STATE_DIR"] = args.state_dir

    if args.command == "demo":
        result = run_demo(
            deliverable_url=args.deliverable_url,
            port=args.port,
            fresh_contract=args.fresh,
            skip_judgment=args.skip_judgment,
        )
        print(json.dumps({"case": result.get("case_id"), "refund_units": result.get("refund_units")}, indent=2))
        return 0

    if args.command == "serve":
        accounts = wallets()
        settler = LocalLedgerSettler(os.path.join(os.environ.get("COURTPAY_STATE_DIR", ".courtpay"), "ledger.json"))
        httpd = serve(accounts["seller"], Catalog(CATALOG), settler, port=args.port, verbose=True)
        print("seller %s listening on http://127.0.0.1:%d" % (accounts["seller"].address, args.port))
        httpd.serve_forever()
        return 0

    if args.command == "buy":
        accounts = wallets()
        delivery = fetch_paid(args.url, accounts["buyer"], max_price=args.max_price)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "receipt": delivery.receipt,
                    "receipt_hash": delivery.receipt_hash,
                    "payment": delivery.payment_response,
                    "body": delivery.json_body(),
                    "requirements": delivery.requirements,
                },
                handle,
                indent=2,
            )
        print("receipt %s → %s" % (delivery.receipt_hash, args.out))
        return 0

    if args.command == "dispute":
        accounts = wallets()
        with open(args.receipt, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        payload = receipts.verify_receipt(stored["receipt"])
        court = Court(accounts["court"].key.hex(), contract=args.contract)
        case = court.open_case(
            seller=payload["seller"],
            resource_url=payload["resource"],
            promise=payload["promise"],
            price_units=int(payload["amount"]),
            asset=payload["asset"],
            receipt_hash=stored["receipt_hash"],
        )
        court.dispute(case["case_id"], args.deliverable_url, args.complaint)
        court.judge(case["case_id"])
        print(json.dumps(court.get_case(case["case_id"]), indent=2))
        return 0

    return 1
