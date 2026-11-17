"""Demo catalog: one dataset whose delivery quietly breaks its promise."""

from __future__ import annotations

from .x402 import BASE_SEPOLIA_USDC

LATENCY_FEED = {
    "title": "Base Sepolia RPC latency feed",
    "promise": (
        "Ten verified RPC endpoints for Base Sepolia. Every row carries region, "
        "endpoint URL, p50 latency, p99 latency and a probe checksum, and every row "
        "was probed within the last 24 hours."
    ),
    "price_units": 250000,
    "asset": BASE_SEPOLIA_USDC,
    "required_fields": ["region", "endpoint", "p50_ms", "p99_ms", "probe_checksum"],
    "expected_rows": 10,
    "delivery": {
        "dataset": "base-sepolia-rpc-latency",
        "probed_at": "2026-11-15T03:40:00Z",
        "note": "Premium endpoint telemetry, refreshed continuously.",
        "rows": [
            {"region": "eu-fra", "endpoint": "https://rpc-eu.example.net", "p50_ms": 41},
            {"region": "us-east", "endpoint": "https://rpc-us.example.net", "p50_ms": 88},
            {"region": "ap-sgp", "endpoint": "https://rpc-sg.example.net", "p50_ms": 132},
        ],
    },
}

CATALOG = {"latency-feed": LATENCY_FEED}
