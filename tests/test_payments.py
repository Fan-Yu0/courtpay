import json
import threading

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from courtpay import receipts
from courtpay.buyer import fetch_paid
from courtpay.catalog import CATALOG
from courtpay.preflight import check_delivery
from courtpay.seller import Catalog, serve
from courtpay.x402 import (
    LocalLedgerSettler,
    X402Error,
    decode_payment_header,
    encode_payment_header,
    payment_requirements,
    sign_payment,
    typed_data,
    verify_payment,
)


@pytest.fixture()
def shop(tmp_path):
    seller = Account.create()
    buyer = Account.create()
    settler = LocalLedgerSettler(str(tmp_path / "ledger.json"))
    httpd = serve(seller, Catalog(CATALOG), settler, port=0)
    httpd.server_address = httpd.server_address
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"seller": seller, "buyer": buyer, "settler": settler, "url": "http://127.0.0.1:%d/dataset/latency-feed" % port}
    httpd.shutdown()
    httpd.server_close()


def _requirements(seller):
    return payment_requirements(
        resource="http://127.0.0.1:9/dataset/latency-feed",
        description="demo",
        pay_to=seller.address,
        amount=250000,
    )


def test_paid_request_returns_signed_receipt(shop):
    delivery = fetch_paid(shop["url"], shop["buyer"])
    payload = receipts.verify_receipt(delivery.receipt)
    assert payload["buyer"].lower() == shop["buyer"].address.lower()
    assert payload["seller"].lower() == shop["seller"].address.lower()
    assert len(delivery.receipt_hash) == 64
    assert delivery.payment_response["success"] is True
    assert delivery.json_body()["dataset"] == "base-sepolia-rpc-latency"


def test_unpaid_request_is_a_402(shop):
    with pytest.raises(X402Error) as excinfo:
        import urllib.request, urllib.error
        try:
            urllib.request.urlopen(shop["url"], timeout=5)
        except urllib.error.HTTPError as error:
            body = json.loads(error.read().decode())
            assert error.code == 402
            assert body["x402Version"] == 1
            assert body["accepts"][0]["maxAmountRequired"] == "250000"
            raise X402Error("expected_402")
    assert excinfo.value.reason == "expected_402"


def test_underpayment_is_rejected(shop):
    requirements = _requirements(shop["seller"])
    payload = sign_payment(shop["buyer"], requirements, value=1000)
    used = set()
    with pytest.raises(X402Error) as excinfo:
        verify_payment(payload, requirements, used)
    assert excinfo.value.reason == "underpaid"
    assert not used


def test_wrong_payee_is_rejected(shop):
    requirements = _requirements(Account.create())
    payload = sign_payment(shop["buyer"], requirements)
    requirements["payTo"] = shop["seller"].address
    with pytest.raises(X402Error) as excinfo:
        verify_payment(payload, requirements, set())
    assert excinfo.value.reason == "wrong_payee"


def test_replayed_nonce_is_rejected(shop):
    requirements = _requirements(shop["seller"])
    payload = sign_payment(shop["buyer"], requirements)
    used = set()
    verify_payment(payload, requirements, used)
    with pytest.raises(X402Error) as excinfo:
        verify_payment(payload, requirements, used)
    assert excinfo.value.reason == "nonce_already_used"


def test_tampered_signature_is_rejected(shop):
    requirements = _requirements(shop["seller"])
    payload = sign_payment(shop["buyer"], requirements)
    signature = payload["payload"]["signature"]
    payload["payload"]["signature"] = signature[:-4] + ("0000" if signature[-4:] != "0000" else "1111")
    with pytest.raises(X402Error) as excinfo:
        verify_payment(payload, requirements, set())
    assert excinfo.value.reason in ("invalid_signature", "nonce_already_used")


def test_preflight_reports_missing_promise_fields():
    check = check_delivery(CATALOG["latency-feed"], CATALOG["latency-feed"]["delivery"])
    assert check["ok"] is False
    assert check["rows"] == 3
    assert "p99_ms" in check["missing_fields"]
    assert "probe_checksum" in check["missing_fields"]
