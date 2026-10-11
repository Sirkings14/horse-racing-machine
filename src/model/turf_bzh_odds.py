from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from src.model.market_evidence import append_snapshot, normalize_snapshot

API_BASE = "https://www.turf.bzh/api/v1"


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def build_snapshot(
    payload: dict[str, Any],
    *,
    race_key: str,
    race_off_at: str,
    source_url: str,
    expected_course_code: str,
    expected_runner_numbers: set[int],
    captured_at: str | None = None,
) -> dict[str, Any] | None:
    """Map a verified Turf.bzh PMU odds response into strict ledger evidence."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("partants"), list):
        return None
    if data.get("source") != "pmu":
        return None
    if str(data.get("code_course") or "").upper() != expected_course_code.upper():
        return None

    response_date = str(data.get("date") or "")
    if not race_key.startswith(response_date + "|"):
        return None

    priced_at = data.get("updated_at") or (payload.get("meta") or {}).get("generated_at")
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()
    priced_time = _timestamp(priced_at)
    off_time = _timestamp(race_off_at)
    capture_time = _timestamp(captured_at)
    if priced_time is None or off_time is None or capture_time is None:
        return None
    if priced_time > capture_time or priced_time > off_time or capture_time > off_time:
        return None

    odds: dict[str, float] = {}
    seen: set[int] = set()
    for runner in data["partants"]:
        if not isinstance(runner, dict) or runner.get("np") is True:
            continue
        try:
            number = int(runner.get("num"))
            price = float(runner.get("cote"))
        except (TypeError, ValueError):
            continue
        if number <= 0 or price <= 1 or number in seen:
            return None
        seen.add(number)
        odds[str(number)] = price

    if not odds or not expected_runner_numbers or set(map(int, odds)) != expected_runner_numbers:
        return None

    return {
        "race_key": race_key,
        "source": "Turf.bzh API (PMU live odds)",
        "source_type": "tote_win",
        "market_type": "winner",
        "source_url": source_url,
        "raw_reference": source_url,
        "captured_at": captured_at,
        "price_timestamp": priced_at,
        "race_off_at": race_off_at,
        "odds": odds,
    }


def fetch_snapshot(
    *,
    race_date: str,
    course_code: str,
    race_key: str,
    race_off_at: str,
    expected_runner_numbers: set[int],
    api_key: str | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    key = api_key or os.environ.get("TURFBZH_API_KEY")
    if not key:
        raise RuntimeError("TURFBZH_API_KEY is not configured.")
    if not course_code or not race_date or not race_key or not race_off_at:
        raise ValueError("race_date, course_code, race_key, and race_off_at are required.")
    url = f"{API_BASE}/courses/{quote(race_date)}/{quote(course_code)}/cotes"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    snapshot = build_snapshot(
        payload,
        race_key=race_key,
        race_off_at=race_off_at,
        source_url=url,
        expected_course_code=course_code,
        expected_runner_numbers=expected_runner_numbers,
    )
    if snapshot is None:
        raise ValueError(
            "Odds response failed provenance, timestamp, source, or runner-roster validation; nothing was recorded."
        )
    if not normalize_snapshot(snapshot):
        raise ValueError("Odds snapshot failed strict market-evidence validation; nothing was recorded.")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a timestamped pre-race PMU win-odds snapshot via Turf.bzh.")
    parser.add_argument("--date", required=True, help="Race date in YYYY-MM-DD")
    parser.add_argument("--course-code", required=True, help="Provider race code, for example R1C4")
    parser.add_argument("--race-key", required=True, help="Validated machine race key: YYYY-MM-DD|TRACK|N")
    parser.add_argument("--race-off-at", required=True, help="Scheduled off time with timezone, e.g. 2026-10-12T10:15:00+02:00")
    parser.add_argument("--runner-numbers", required=True, help="Comma-separated expected active runner numbers")
    args = parser.parse_args()

    try:
        runner_numbers = {int(value.strip()) for value in args.runner_numbers.split(",") if value.strip()}
        if not runner_numbers:
            raise ValueError("At least one expected runner number is required.")
        snapshot = fetch_snapshot(
            race_date=args.date,
            course_code=args.course_code,
            race_key=args.race_key,
            race_off_at=args.race_off_at,
            expected_runner_numbers=runner_numbers,
        )
        accepted = append_snapshot(snapshot)
    except (requests.RequestException, ValueError, RuntimeError) as error:
        parser.error(str(error))
        return 2

    print(f"Race: {snapshot['race_key']}")
    print(f"Provider price timestamp: {snapshot['price_timestamp']}")
    print(f"Captured at: {snapshot['captured_at']}")
    print(f"Runner prices: {len(snapshot['odds'])}")
    print("Evidence saved." if accepted else "Valid snapshot was already recorded; no duplicate added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
