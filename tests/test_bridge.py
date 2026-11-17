from courtpay.bridge import GUIDELINES, to_internet_court_case


CASE = {
    "case_id": "case-1",
    "buyer": "0xBuyer",
    "seller": "0xSeller",
    "resource_url": "http://127.0.0.1:8402/dataset/latency-feed",
    "promise": "Ten verified rows with p99 and checksums.",
    "complaint": "Delivered 3 rows with no p99.",
    "deliverable_url": "https://cdn.example.com/delivery.json",
    "price_units": 250000,
    "asset": "0xUSDC",
    "receipt_hash": "ab" * 32,
    "state": 2,
    "verdict": 0,
    "confidence": "high",
    "reasoning": "Three rows, no p99.",
    "round": 1,
}


def test_refund_maps_to_party_a():
    payload = to_internet_court_case(CASE)
    assert payload["verdict"] == "PARTY_A"
    assert payload["parties"]["party_a"] == "0xBuyer"
    assert payload["parties"]["party_b"] == "0xSeller"
    assert payload["evidence"]["party_a"][0]["url"] == "https://cdn.example.com/delivery.json"
    assert payload["payment"]["receipt_hash"] == "ab" * 32
    assert payload["guidelines"] == GUIDELINES


def test_no_refund_maps_to_party_b():
    payload = to_internet_court_case({**CASE, "verdict": 1})
    assert payload["verdict"] == "PARTY_B"


def test_undetermined_stays_undetermined():
    payload = to_internet_court_case({**CASE, "verdict": 2})
    assert payload["verdict"] == "UNDETERMINED"


def test_statement_carries_promise_and_complaint():
    payload = to_internet_court_case(CASE)
    assert CASE["promise"] in payload["statement"]
    assert CASE["complaint"] in payload["statement"]
