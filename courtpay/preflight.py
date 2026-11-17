"""Deterministic buyer-side check that runs before anyone goes to court."""

from __future__ import annotations

from typing import Any, Dict, List


def check_delivery(entry: Dict[str, Any], delivery: Any) -> Dict[str, Any]:
    problems: List[str] = []
    rows = delivery.get("rows") if isinstance(delivery, dict) else None

    if not isinstance(rows, list):
        return {"ok": False, "problems": ["delivery is not a dataset with rows"], "missing_fields": [], "rows": 0}

    expected_rows = int(entry.get("expected_rows", 0))
    if expected_rows and len(rows) < expected_rows:
        problems.append("delivered %d of %d promised rows" % (len(rows), expected_rows))

    missing_fields: List[str] = []
    for field in entry.get("required_fields", []):
        if not all(isinstance(row, dict) and field in row for row in rows):
            missing_fields.append(field)
    if missing_fields:
        problems.append("rows are missing: " + ", ".join(missing_fields))

    return {
        "ok": not problems,
        "problems": problems,
        "missing_fields": missing_fields,
        "rows": len(rows),
    }
