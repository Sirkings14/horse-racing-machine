from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[2]
LEDGER_FILE = BASE_DIR / "data" / "evaluation" / "market_evidence.json"

SUPPORTED_MARKETS = {"winner", "place", "exacta", "trifecta", "quartet", "quinte"}
SUPPORTED_PRICE_SOURCES = {"bookmaker_win", "tote_win", "exchange_win"}
RACE_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\|[^|]+\|\d{1,2}$")


def _parse_aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 1.0 else None


def normalize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Validate source-attributed pre-race prices and their capture timestamps.

    Press estimates, model probabilities, result-time prices, and snapshots
    without an auditable source/timestamp are not economic market evidence.
    """
    if not isinstance(snapshot, dict):
        return None

    race_key = str(snapshot.get("race_key") or "").strip()
    source = str(snapshot.get("source") or "").strip()
    source_type = str(snapshot.get("source_type") or "").strip().lower()
    market = str(snapshot.get("market_type") or "winner").strip().lower()
    source_url = str(snapshot.get("source_url") or snapshot.get("raw_reference") or "").strip()

    captured = _parse_aware_timestamp(snapshot.get("captured_at"))
    priced = _parse_aware_timestamp(snapshot.get("price_timestamp"))
    race_off = _parse_aware_timestamp(snapshot.get("race_off_at"))

    if not RACE_KEY_RE.fullmatch(race_key):
        return None
    if not source or source_type not in SUPPORTED_PRICE_SOURCES:
        return None
    if market not in SUPPORTED_MARKETS:
        return None
    parsed_url = urlparse(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return None
    if captured is None or priced is None or race_off is None:
        return None
    if priced > captured or captured > race_off or priced > race_off:
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
            if horse > 0 and price is not None:
                prices[horse] = price
    if not prices:
        return None

    # Preserve per-runner quote-update times when a source explicitly provides
    # them. They are supplementary provenance; price_timestamp remains the time
    # this complete quote response was observed by the collector.
    runner_price_timestamps: dict[int, str] = {}
    raw_runner_times = snapshot.get("runner_price_timestamps")
    if isinstance(raw_runner_times, dict):
        for number, value in raw_runner_times.items():
            try:
                horse = int(number)
            except (TypeError, ValueError):
                continue
            if horse not in prices:
                continue
            parsed = _parse_aware_timestamp(value)
            if parsed is None or parsed > captured or parsed > race_off:
                return None
            runner_price_timestamps[horse] = parsed.isoformat()

    normalized = {
        "race_key": race_key,
        "captured_at": captured.isoformat(),
        "source": source,
        "source_type": source_type,
        "market_type": market,
        "odds": prices,
        "official_dividends": snapshot.get("official_dividends") or {},
        "price_timestamp": priced.isoformat(),
        "race_off_at": race_off.isoformat(),
        "source_url": source_url,
        "raw_reference": snapshot.get("raw_reference") or source_url,
        "evidence_grade": "verified_pre_race_market_odds",
        "observed": True,
    }
    if runner_price_timestamps:
        normalized["runner_price_timestamps"] = runner_price_timestamps
    return normalized


def observed_snapshots_for_race(race_key: str, market_type: str = "winner") -> list[dict[str, Any]]:
    """Return explicitly observed snapshots for one race, newest first."""
    rows = [
        row for row in load_ledger()
        if isinstance(row, dict)
        and row.get("observed") is True
        and row.get("evidence_grade") == "verified_pre_race_market_odds"
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
        normalized["source_type"],
        normalized["market_type"],
        normalized["captured_at"],
    )
    if any(
        (
            row.get("race_key"), row.get("source"), row.get("source_type"),
            row.get("market_type"), row.get("captured_at"),
        ) == identity
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
        "source_type": None,
        "market_type": "winner",
        "odds": {},
        "observed": False,
        "status": "unavailable",
        "policy": {
            "never_invent_odds": True,
            "probabilities_are_not_prices": True,
            "press_estimates_are_not_market_odds": True,
        },
    }
