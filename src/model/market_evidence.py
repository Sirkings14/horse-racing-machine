from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
LEDGER_FILE = BASE_DIR / "data" / "evaluation" / "market_evidence.json"

SUPPORTED_MARKETS = {"winner", "place", "exacta", "trifecta", "quartet", "quinte"}


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 1.0 else None


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Accept only explicitly observed market prices; never infer them."""
    race_key = str(snapshot.get("race_key") or "").strip()
    source = str(snapshot.get("source") or "").strip()
    market = str(snapshot.get("market_type") or "winner").strip().lower()
    captured_at = str(snapshot.get("captured_at") or "").strip()
    if not race_key or not source or market not in SUPPORTED_MARKETS or not captured_at:
        return None

    prices: dict[int, float] = {}
    raw_prices = snapshot.get("odds")
    if isinstance(raw_prices, dict):
        for number, value in raw_prices.items():
            try:
                horse = int(number)
            except (TypeError, ValueError):
                continue
            price = _positive_float(value)
            if price is not None:
                prices[horse] = price
    if not prices:
        return None

    return {
        "race_key": race_key,
        "captured_at": captured_at,
        "source": source,
        "market_type": market,
        "odds": prices,
        "official_dividends": snapshot.get("official_dividends") or {},
        "price_timestamp": snapshot.get("price_timestamp"),
        "raw_reference": snapshot.get("raw_reference"),
        "observed": True,
    }


def observed_snapshots_for_race(race_key: str, market_type: str = "winner") -> list[dict[str, Any]]:
    """Return explicitly observed snapshots for one race, newest first."""
    rows = [
        row for row in load_ledger()
        if isinstance(row, dict)
        and row.get("observed") is True
        and row.get("race_key") == race_key
        and row.get("market_type", "winner") == market_type
    ]
    return sorted(rows, key=lambda row: str(row.get("captured_at", "")), reverse=True)


def latest_observed_snapshot(race_key: str, market_type: str = "winner") -> dict[str, Any] | None:
    rows = observed_snapshots_for_race(race_key, market_type)
    return rows[0] if rows else None


def load_ledger() -> list[dict[str, Any]]:
    try:
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def append_snapshot(snapshot: dict[str, Any]) -> bool:
    normalized = normalize_snapshot(snapshot)
    if normalized is None:
        return False
    rows = load_ledger()
    identity = (
        normalized["race_key"],
        normalized["source"],
        normalized["market_type"],
        normalized["captured_at"],
    )
    if any(
        (row.get("race_key"), row.get("source"), row.get("market_type"), row.get("captured_at")) == identity
        for row in rows if isinstance(row, dict)
    ):
        return False
    rows.append(normalized)
    rows.sort(key=lambda row: (str(row.get("captured_at")), str(row.get("race_key"))))
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def build_unavailable_record(race_key: str, captured_at: str | None = None) -> dict[str, Any]:
    return {
        "race_key": race_key,
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "source": None,
        "market_type": "winner",
        "odds": {},
        "observed": False,
        "status": "unavailable",
        "policy": {
            "never_invent_odds": True,
            "probabilities_are_not_prices": True,
        },
    }
