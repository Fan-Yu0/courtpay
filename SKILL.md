---
name: courtpay
description: Buy paid x402 resources with an adjudicated refund path. Use when an agent needs a paid dataset or API result where a bad delivery must be provable and reversible, or when a buyer and seller want an Internet Court style case over a specific delivery.
---

# CourtPay

CourtPay gives an agent two things x402 alone does not: a signed receipt that
pins a purchase to a promise, and a dispute path where a GenLayer jury decides
whether the delivery matched that promise.

## When to use

- You are about to pay an x402-protected endpoint and the value of the artifact
  matters (data, reports, prices, generated content).
- A paid delivery arrived and does not match what was advertised.
- You want a refund decision that is reasoned and auditable instead of trusting
  the seller's support inbox.

Do not use this skill when the payment is trivially refundable, when the resource
is not paid, or when you have no receipt. Without a receipt there is no case.

## Buying

```bash
python -m courtpay buy --url https://seller.example/dataset/alpha --max-price 250000 --out receipt.json
```

- Always pass `--max-price`. It is your budget gate; the buyer agent refuses a
  challenge above it.
- The receipt file contains the seller's signature, the payment reference, the
  delivery hash and the promise. Keep it; it is your standing.

## Checking before you accuse

Run the deterministic check first. If the artifact obviously satisfies the
promise, do not open a case.

```python
from courtpay.preflight import check_delivery
check_delivery(entry, payload)   # -> {"ok": bool, "problems": [...], "missing_fields": [...]}
```

## Disputing

```bash
python -m courtpay dispute \
  --receipt receipt.json \
  --deliverable-url https://public.example/deliveries/alpha.json \
  --complaint "Delivered 3 of 10 rows; every row is missing p99 and a checksum."
```

Rules:

- The delivery URL must be publicly reachable. GenLayer validators fetch it
  themselves; `file://`, `localhost` and private networks will come back as
  `insufficient_evidence` and refund the buyer.
- The complaint must name the concrete deviation. "Bad data" is not a complaint;
  "3 of 10 rows, no p99_ms, no probe_checksum" is.
- One case per receipt hash. Re-opening the same receipt is a bug in the caller.

## Reading the verdict

| Field | Meaning |
| --- | --- |
| `verdict = 0` | `REFUND` — the delivery violated the promise |
| `verdict = 1` | `NO_REFUND` — the delivery fulfilled the promise |
| `verdict = 2` | `UNDETERMINED` — the artifact could not settle the claim; money returns to the buyer |
| `confidence` | `high` / `medium` / `low`, straight from the jury |
| `reasoning` | Two sentences citing the artifact; stored on-chain |
| `evidence_excerpt` | The fragment that decided the case |
| `refund_units` | `price_units` or `0`; never disagrees with the verdict |

The seller may `appeal` a resolved case once per round; the case returns to
`disputed` and the jury runs again.

## Guardrails

- Never claim a refund happened just because a verdict says `REFUND`. The money
  moves when the settlement job reads `refund_amount` — report both the verdict
  and the applied refund separately.
- Do not describe the demo settler as on-chain settlement. In the default
  configuration the payment reference is `local:0x…`.
- Do not ask for private keys; the CLI reads wallets from `.courtpay/`.

## Reference

- `README.md` — architecture, layout, settlement adapters, honest scope
- `contracts/courtpay_court.py` — the jury and case store
- `tests/direct/` — the contract behaviour the skill relies on
