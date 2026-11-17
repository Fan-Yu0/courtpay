# CourtPay

**x402 payments are final. CourtPay makes them reversible — by a jury, not a support inbox.**

CourtPay is a small, working integration between three Internet Court stack members:

| Logo | Role in this demo |
| --- | --- |
| **x402** | Per-request payment rail. The seller answers `402 Payment Required`; the buyer pays with a signed EIP-3009 authorization. |
| **GenLayer** | The jury. An Intelligent Contract fetches the delivered artifact and judges it against what the seller promised. |
| **Internet Court** | The case model and the dispute lifecycle: statement, guidelines, evidence, verdict, reasoning, appeal. |

When an agent buys data, an API result or a generated report over x402, the payment
settles before the artifact is read. Today the only recourse for a bad delivery is
a human support ticket. CourtPay turns that into a case: the buyer files one with
the signed receipt, GenLayer validators independently fetch the delivery and judge
it, and the verdict decides the refund deterministically.

## What runs in the demo

```text
seller   GET /dataset/latency-feed
         402 Payment Required  ·  exact  ·  base-sepolia  ·  250000 (0.25 USDC)
buyer    signs EIP-3009 transferWithAuthorization → 200 OK + signed receipt
buyer    preflight: 3 of 10 rows, missing p99_ms, probe_checksum
court    case-1 opened from the receipt hash → dispute filed with delivery URL
jury     validators fetch the delivery themselves and re-run the review
jury     VIOLATED · high confidence · 3 rows, no p99 latency, no probe checksum
result   refund 250000 of 250000 units
```

Everything above is real except settlement: the demo uses a **local settler** that
records the authorized transfer in `ledger.json`. The authorization itself is a
genuine EIP-3009 payload, so the same bytes can be handed to a hosted x402
facilitator without changing the handshake (see [Settlement adapters](#settlement-adapters)).

## Live case (GenLayer Studio Network)

| Field | Value |
| --- | --- |
| Contract | `0x533f3b4b9D6BE050fD64fa23e577Ab5918E46b10` |
| Case | `case-1` |
| Verdict | `REFUND` (0) · confidence `high` |
| Refund | `250000 / 250000` units |
| Evidence judged | https://raw.githubusercontent.com/Fan-Yu0/courtpay/master/demo/deliveries/latency-feed.json |

Jury reasoning, stored on-chain with the verdict:

> The delivery only contains 3 rows instead of the promised 10, and it is
> missing the required p99 latency and probe checksum fields for each row.

Check it yourself:

```bash
python -c "from courtpay.court import Court; from courtpay.demo import wallets; \
c = Court(wallets()['court'].key.hex(), contract='0x533f3b4b9D6BE050fD64fa23e577Ab5918E46b10'); \
print(c.get_case('case-1'))"
```

The full record, including the receipt hash and the raw delivery, is in
`evidence/live.json` and `demo/run-raw.txt`.

## Demo video

`demo/courtpay-demo.mp4` — 45s, generated from the real transcript by
`demo/make_video.py`.

## Why GenLayer

A delivery either matches the promise or it does not — and "matches" is a
judgment about unstructured content: a dataset missing two columns, a report that
is only an abstract, a feed whose checksums do not correspond to any probe. That
is exactly the work an LLM jury does well and a static rules engine does badly.

CourtPay therefore puts only the *judgment* on GenLayer and keeps everything else
deterministic:

- validators fetch the delivery themselves; they never trust the leader's copy;
- validators must agree on the verdict band (`fulfilled` / `violated` /
  `insufficient_evidence`) — an exact match, no tolerance;
- the refund is a pure function of the agreed band, so a verdict can never
  disagree with the money it releases;
- the reasoning and the deciding fragment of the artifact are stored on-chain,
  which is what makes an appeal meaningful.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m courtpay demo --fresh
```

`demo` starts the x402 seller on `127.0.0.1:8402`, pays it as a buyer agent,
checks the delivery, deploys the court contract to GenLayer Studio, files the
dispute and waits for the jury. Wallets and the contract address live in
`.courtpay/` and are reused on later runs.

To point the jury at a delivery hosted anywhere public:

```bash
python -m courtpay demo --deliverable-url https://cdn.example.com/latency-feed.json
```

The jury needs a public URL because validators fetch evidence on their own
infrastructure — `file://` and `localhost` are not reachable from there.

## Layout

```text
contracts/courtpay_court.py   GenLayer Intelligent Contract (jury + case store)
courtpay/x402.py              x402 v1 "exact" scheme, sign / verify / settle
courtpay/seller.py            402-protected seller with signed receipts
courtpay/buyer.py             paid fetch + receipt verification
courtpay/preflight.py         buyer-side deterministic check (before court)
courtpay/court.py             GenLayer client: deploy, open, dispute, judge
courtpay/demo.py              the end-to-end run
tests/direct/                 10 direct-mode contract tests (mock web + LLM)
tests/test_payments.py        7 x402 tests: underpay, replay, tamper, wrong payee
demo/deliveries/              the artifact the jury is asked to judge
```

## Contract interface

| Method | Type | Purpose |
| --- | --- | --- |
| `open_case(seller, resource_url, promise, price_units, asset, receipt_hash)` | write | Buyer records the purchase and the promise it was sold under |
| `dispute(case_id, deliverable_url, complaint)` | write | Buyer only, once, with the public delivery URL |
| `judge(case_id)` | write | Permissionless; runs the non-deterministic review under consensus |
| `appeal(case_id)` | write | Seller only, on a resolved case; returns it to `disputed` for another round |
| `get_case(case_id)` | view | Full case: parties, promise, complaint, verdict, reasoning, evidence excerpt |
| `refund_amount(case_id)` | view | `price_units` for `REFUND`/`UNDETERMINED`, `0` for `NO_REFUND` |
| `list_cases()` / `get_stats()` | view | Enumeration and counters |

Verdict bands: `fulfilled → NO_REFUND`, `violated → REFUND`,
`insufficient_evidence → UNDETERMINED` (escrow returns to the buyer, matching
Internet Court's rule that an unprovable claim must not silently keep the money).

## Internet Court mapping

`courtpay/bridge.py` turns a resolved case into the Internet Court v1 jury
payload, so the same dispute can be replayed into Internet Court's contract and
surfaced on internetcourt.org:

| CourtPay | Internet Court v1 |
| --- | --- |
| `promise` + `complaint` | `statement` |
| review rubric | `guidelines` |
| buyer + delivery URL | `party_a` evidence |
| seller | `party_b` (no counter-evidence is a valid, losing default) |
| `REFUND` / `NO_REFUND` / `UNDETERMINED` | `PARTY_A` / `PARTY_B` / `UNDETERMINED` |
| `receipt_hash` | payment block on the Base escrow side |

The verdict band is the only commitment; the reasoning is stored on both sides
so an appeal reads the same evidence trail.

## Settlement adapters

`x402.py` exposes one seam:

```python
settler.settle(authorization, requirements) -> payment_reference
```

- `LocalLedgerSettler` (default): appends the authorization to `ledger.json`.
- Production: implement `FacilitatorSettler` that POSTs the payload to an x402
  facilitator (`/verify` then `/settle`) for `base-sepolia` or `base`, and return
  the on-chain transaction hash. Nothing else in the demo changes.

## Honest scope

- Settlement is local; no funds move in the default demo. This is labelled in
  every transcript line and in the receipt (`paymentRef: local:0x…`).
- The court is deployed on GenLayer Studio Network; the case model mirrors
  Internet Court v1 but the LayerZero bridge to Base is **not** wired here.
  A case id and its evidence are already in the shape the bridge expects.
- Refunds are applied by the caller of `refund_amount` (the seller's settlement
  job or the buyer's wallet). CourtPay decides; it does not custody.

## Tests

```bash
pytest tests/direct -q            # 10 contract tests, mock web + LLM
pytest tests/test_payments.py -q  # 7 x402 protocol tests
pytest tests/test_bridge.py -q    # 4 Internet Court mapping tests
genvm-lint check contracts/courtpay_court.py
```

## License

MIT
