#!/usr/bin/env python3
"""Audit the public Open PMU API's historical cotes fields without treating them as pre-race evidence.

This is an exploratory diagnostic only. It deliberately does not write to the
market-evidence ledger and does not estimate or claim the timestamp represented
by any value in a historical cotes array.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://open-pmu-api.vercel.app/api/arrivees"


def fetch_date(date_text: str, timeout: float = 15.0) -> dict:
    parsed = datetime.strptime(date_text, "%m/%d/%Y")
    query = urlencode({"date": parsed.strftime("%m/%d/%Y")})
    request = Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "horse-racing-machine-odds-source-audit/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Open PMU API returned HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), list):
        raise ValueError("Unexpected API response shape: expected object with a message list")
    return payload


def audit_payload(payload: dict) -> dict:
    races = payload.get("message", [])
    price_list_lengths: Counter[int] = Counter()
    runner_rows = 0
    rows_with_cotes = 0
    rows_with_explicit_price_timestamp = 0
    sample_cotes: list[list[object]] = []

    for race in races:
        if not isinstance(race, dict):
            continue
        details = race.get("arrivee_details", {})
        if not isinstance(details, dict):
            continue
        for runner in details.values():
            if not isinstance(runner, dict):
                continue
            runner_rows += 1
            cotes = runner.get("cotes")
            if isinstance(cotes, list):
                rows_with_cotes += 1
                price_list_lengths[len(cotes)] += 1
                if len(sample_cotes) < 5:
                    sample_cotes.append(cotes)
            if any(key in runner for key in ("cote_timestamp", "cotes_timestamp", "price_timestamp", "odds_timestamp")):
                rows_with_explicit_price_timestamp += 1

    return {
        "race_count": len(races),
        "runner_rows_in_arrivee_details": runner_rows,
        "runner_rows_with_cotes_array": rows_with_cotes,
        "cotes_array_length_distribution": dict(sorted(price_list_lengths.items())),
        "runner_rows_with_explicit_price_timestamp_field": rows_with_explicit_price_timestamp,
        "sample_cotes_arrays": sample_cotes,
        "decision": "EXPLORATORY_ONLY_NOT_PRE_RACE_EVIDENCE",
        "reason": (
            "The documented historical response does not define which moments the cotes values represent "
            "or provide an auditable price timestamp. Do not import these values into market_evidence.json."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Race date in MM/DD/YYYY format")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    try:
        payload = fetch_date(args.date, timeout=args.timeout)
        report = audit_payload(payload)
    except (ValueError, RuntimeError, HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        parser.error(f"Source audit failed: {exc}")
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
