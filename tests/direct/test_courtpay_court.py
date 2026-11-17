import json

from conftest import to_hex

CONTRACT = "contracts/courtpay_court.py"
SELLER_URL = "https://seller.example.com/dataset/latency-feed"
DELIVERY_URL = "https://cdn.example.com/deliveries/latency-feed.json"
PROMISE = "Ten verified RPC endpoints with region, p50 latency, p99 latency and a probe checksum."
RECEIPT = "ab" * 32

BAD_DELIVERY = '{"rows":[{"region":"eu-fra","p50_ms":41}],"probe":"none"}'
GOOD_DELIVERY = json.dumps(
    {"rows": [{"region": "eu-%d" % i, "p50_ms": 40 + i, "p99_ms": 90 + i, "probe_checksum": "0xabc"} for i in range(10)]}
)


def _mock(vm, delivery, finding):
    vm.mock_web(r".*cdn\.example\.com/deliveries/latency-feed\.json.*", {"status": 200, "body": delivery})
    vm.mock_llm(r".*DELIVERY DISPUTE REVIEW.*", json.dumps(finding))


def _violated():
    return {
        "verdict": "violated",
        "confidence": "high",
        "reasoning": "Delivered one row with no p99 latency and no probe checksum.",
        "evidence_excerpt": '{"region":"eu-fra","p50_ms":41}',
    }


def _fulfilled():
    return {
        "verdict": "fulfilled",
        "confidence": "high",
        "reasoning": "Ten rows, each with p50, p99 and a probe checksum.",
        "evidence_excerpt": '{"region":"eu-0","probe_checksum":"0xabc"}',
    }


def _open(contract, vm, buyer, seller, price=250000):
    vm.sender = buyer
    return contract.open_case(to_hex(seller), SELLER_URL, PROMISE, price, "USDC", RECEIPT)


def _dispute(contract, vm, buyer, case_id, complaint="Delivered 1 of 10 rows and no checksum."):
    vm.sender = buyer
    contract.dispute(case_id, DELIVERY_URL, complaint)


def test_violated_delivery_is_refunded(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    _dispute(contract, direct_vm, direct_alice, case_id)
    _mock(direct_vm, BAD_DELIVERY, _violated())

    contract.judge(case_id)

    case = contract.get_case(case_id)
    assert case["state"] == 2
    assert case["verdict"] == 0
    assert case["confidence"] == "high"
    assert "p99" in case["reasoning"]
    assert contract.refund_amount(case_id) == 250000


def test_fulfilled_delivery_keeps_the_payment(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    _dispute(contract, direct_vm, direct_alice, case_id)
    _mock(direct_vm, GOOD_DELIVERY, _fulfilled())

    contract.judge(case_id)

    case = contract.get_case(case_id)
    assert case["verdict"] == 1
    assert contract.refund_amount(case_id) == 0


def test_unreadable_delivery_is_undetermined_and_refunded(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    _dispute(contract, direct_vm, direct_alice, case_id)
    direct_vm.mock_web(r".*cdn\.example\.com.*", {"status": 500, "body": ""})

    contract.judge(case_id)

    case = contract.get_case(case_id)
    assert case["verdict"] == 2
    assert case["confidence"] == "low"
    assert contract.refund_amount(case_id) == 250000


def test_only_the_buyer_can_open_the_dispute(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)

    direct_vm.sender = direct_bob
    try:
        contract.dispute(case_id, DELIVERY_URL, "seller trying to force a verdict")
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_judgment_requires_a_disputed_case(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)

    try:
        contract.judge(case_id)
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_seller_can_appeal_a_resolved_case(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    _dispute(contract, direct_vm, direct_alice, case_id)
    _mock(direct_vm, BAD_DELIVERY, _violated())
    contract.judge(case_id)

    direct_vm.sender = direct_bob
    contract.appeal(case_id)

    case = contract.get_case(case_id)
    assert case["state"] == 1
    assert case["round"] == 2
    assert contract.refund_amount(case_id) == 0


def test_promise_must_describe_the_deliverable(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    try:
        contract.open_case(to_hex(direct_bob), SELLER_URL, "cheap data", 1000, "USDC", RECEIPT)
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_plain_http_evidence_is_rejected(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    try:
        contract.dispute(case_id, "http://cdn.example.com/delivery.json", "no checksum")
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_loopback_resource_url_is_accepted_for_local_sellers(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    case_id = contract.open_case(
        to_hex(direct_bob), "http://127.0.0.1:8402/dataset/latency-feed", PROMISE, 1000, "USDC", RECEIPT
    )
    assert contract.get_case(case_id)["resource_url"].startswith("http://127.0.0.1")


def test_stats_track_disputes_and_refunds(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    case_id = _open(contract, direct_vm, direct_alice, direct_bob)
    _dispute(contract, direct_vm, direct_alice, case_id)
    _mock(direct_vm, BAD_DELIVERY, _violated())
    contract.judge(case_id)

    stats = contract.get_stats()
    assert stats["cases"] == 1
    assert stats["disputed"] == 0
    assert stats["refunded"] == 1
    assert contract.list_cases() == [case_id]
