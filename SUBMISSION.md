# Portal submission draft — Internet Court: Partner Demo Lab

## One line

CourtPay: x402 payments that can be appealed — an AI jury on GenLayer decides whether a paid delivery kept its promise, and the verdict releases the refund.

## Partner

**x402** (founding Internet Court member, payment rail). Internet Court supplies the case model and the dispute lifecycle; GenLayer is the jury.

## What was built

An end-to-end, reproducible integration:

1. A seller exposes a dataset behind an x402 v1 `exact` paywall. The buyer agent receives `402 Payment Required`, signs a real EIP-3009 `transferWithAuthorization`, retries, and gets the artifact plus a **seller-signed receipt** that pins resource, promise, amount, payment reference and delivery hash.
2. A deterministic buyer-side preflight compares the artifact with the promise (`3 of 10 rows`, `missing p99_ms, probe_checksum`).
3. The receipt becomes a case on a GenLayer Intelligent Contract (`CourtPayCourt`). The buyer files the dispute with the public delivery URL.
4. GenLayer validators **fetch the delivery themselves** and re-run the same review; they must agree on the verdict band exactly. Verdict → refund is a pure function, so the money can never disagree with the reasoning.
5. Verdict, confidence, reasoning and the deciding fragment are stored on-chain; the seller can appeal a resolved case.

## Live evidence (GenLayer Studio Network, chain 61999)

- Contract: `0x533f3b4b9D6BE050fD64fa23e577Ab5918E46b10`
- Case: `case-1` — verdict `REFUND`, confidence `high`, refund `250000 / 250000` units
- Jury reasoning: "The delivery only contains 3 rows instead of the promised 10, and it is missing the required p99 latency and probe checksum fields for each row."
- Delivery judged: https://raw.githubusercontent.com/Fan-Yu0/courtpay/master/demo/deliveries/latency-feed.json
- Full record: `evidence/live.json` in the repo

## Reproducible interface

- Repository: https://github.com/Fan-Yu0/courtpay
- One command: `python -m courtpay demo --fresh`
- Agent skill: `SKILL.md` (buy → preflight → dispute → read verdict), installable as a Codex-style skill
- Tests: 21 (10 contract, 7 x402 protocol, 4 Internet Court case mapping) covering underpay, replay, tampered signature, wrong payee, appeal and verdict mapping

## What is real / what is local

- Real: x402 handshake and EIP-3009 signature verification, receipts, the GenLayer contract, validator consensus, on-chain verdict and reasoning.
- Local: settlement. The demo uses a `local-ledger` settler so no funds move; the same authorization bytes can be given to a hosted x402 facilitator (`README.md` → Settlement adapters).
- Not wired: the LayerZero bridge to Base. Case ids and evidence already have the Internet Court v1 shape the bridge expects.

## Video

45s, three logos (Internet Court, GenLayer, x402): `demo/courtpay-demo.mp4`
