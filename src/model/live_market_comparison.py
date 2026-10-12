from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.model.market_evidence import load_ledger, normalize_snapshot

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
OUTPUT_FILE = BASE_DIR / "data" / "evaluation" / "live_market_comparison.json"
MAX_COMPARISON_ROWS = 1000


def _aware_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _safe_race_filename(race_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", race_key)
    return f"{safe}_v3.json"


def _as_valid_probability(row: dict[str, Any]) -> float | None:
    try:
        value = float(row.get("probability_winner"))
        int(row.get("horse_number"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def _prediction_matches_snapshot(prediction: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if prediction.get("race_key") != snapshot.get("race_key"):
        return False
    generated = _aware_utc(prediction.get("generated_at"))
    captured = _aware_utc(snapshot.get("captured_at"))
    off_time = _aware_utc(snapshot.get("race_off_at"))
    if generated is None or captured is None or off_time is None:
        return False
    # Only compare probabilities genuinely available before the observed market
    # snapshot and before the race off-time. No after-the-fact predictions.
    return generated <= captured < off_time


def build_comparison(
    prediction: dict[str, Any],
    raw_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a research-only comparison; never produce a betting recommendation."""
    if not isinstance(prediction, dict) or not isinstance(raw_snapshot, dict):
        return None

    snapshot = normalize_snapshot(raw_snapshot)
    if snapshot is None or not _prediction_matches_snapshot(prediction, snapshot):
        return None
    if snapshot.get("market_type", "winner") != "winner":
        return None

    ranked = prediction.get("ranked_horses")
    if not isinstance(ranked, list) or not ranked:
        return None

    odds: dict[int, float] = {}
    for raw_number, raw_price in (snapshot.get("odds") or {}).items():
        try:
            number = int(raw_number)
            price = float(raw_price)
        except (TypeError, ValueError, OverflowError):
            continue
        if number > 0 and math.isfinite(price) and price > 1.0:
            odds[number] = price

    matched: list[dict[str, Any]] = []
    valid_ranked_count = 0
    for index, horse in enumerate(ranked, start=1):
        if not isinstance(horse, dict):
            continue
        probability = _as_valid_probability(horse)
        if probability is None:
            continue
        valid_ranked_count += 1
        try:
            number = int(horse.get("horse_number"))
        except (TypeError, ValueError, OverflowError):
            continue
        price = odds.get(number)
        if price is None:
            continue

        raw_implied = 1.0 / price
        if not math.isfinite(raw_implied) or raw_implied <= 0.0:
            continue
        try:
            model_rank = int(horse.get("predicted_rank") or index)
        except (TypeError, ValueError, OverflowError):
            model_rank = index

        matched.append({
            "horse_number": number,
            "horse_name": str(horse.get("horse_name") or ""),
            "model_rank": model_rank,
            "market_odds_decimal": price,
            "model_probability_winner": probability,
            "raw_market_implied_probability": raw_implied,
        })

    if valid_ranked_count == 0 or len(matched) / valid_ranked_count < 0.80:
        return None

    implied_total = sum(row["raw_market_implied_probability"] for row in matched)
    if not math.isfinite(implied_total) or implied_total <= 0:
        return None

    for row in matched:
        market_share = row["raw_market_implied_probability"] / implied_total
        row["normalized_market_share"] = market_share
        row["model_minus_market_share"] = row["model_probability_winner"] - market_share

    market_order = sorted(
        matched,
        key=lambda row: (-row["normalized_market_share"], row["horse_number"]),
    )
    for rank, row in enumerate(market_order, start=1):
        row["market_rank"] = rank

    matched.sort(key=lambda row: (row["model_rank"], row["horse_number"]))
    decision = str(prediction.get("live_decision") or "UNSPECIFIED").upper()
    recommended = prediction.get("recommended_numbers") or []
    no_bet = decision in {"NO_BET", "NO BET"} or not recommended

    return {
        "comparison_id": f'{snapshot["race_key"]}|{snapshot["captured_at"]}',
        "race_key": snapshot["race_key"],
        "race": prediction.get("race") or {},
        "prediction_generated_at": prediction.get("generated_at"),
        "snapshot_captured_at": snapshot["captured_at"],
        "price_timestamp": snapshot["price_timestamp"],
        "race_off_at": snapshot["race_off_at"],
        "source": snapshot["source"],
        "source_type": snapshot["source_type"],
        "source_url": snapshot["source_url"],
        "model_version": prediction.get("model_version"),
        "model_fingerprint": prediction.get("model_fingerprint"),
        "live_decision": "NO_BET" if no_bet else decision,
        "confidence": prediction.get("confidence"),
        "model_agreement": prediction.get("model_agreement"),
        "recommended_numbers": recommended,
        "no_bet_reason": prediction.get("no_bet_reason") or [],
        "runner_count": len(matched),
        "runner_comparison": matched,
        "interpretation": (
            "Normalized implied market shares are a margin-normalized price benchmark, "
            "not calibrated true probabilities. Differences are descriptive research signals only."
        ),
        "research_only": True,
        "real_money_authorized": False,
        "decision_policy_preserved": True,
        "roi_claim_permitted": False,
    }


def _load_prediction_for_race(race_key: str) -> dict[str, Any] | None:
    path = PREDICTIONS_DIR / _safe_race_filename(race_key)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> dict[str, Any]:
    ledger = load_ledger()
    existing: dict[str, Any] = {}
    try:
        payload = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            existing = payload
    except (OSError, json.JSONDecodeError):
        pass

    old_rows = existing.get("comparisons")
    by_id = {
        str(row.get("comparison_id")): row
        for row in old_rows
        if isinstance(old_rows, list) and isinstance(row, dict) and row.get("comparison_id")
    } if isinstance(old_rows, list) else {}
    matched_this_run = 0

    for raw_snapshot in ledger:
        if not isinstance(raw_snapshot, dict):
            continue
        race_key = str(raw_snapshot.get("race_key") or "")
        if not race_key:
            continue
        prediction = _load_prediction_for_race(race_key)
        if prediction is None:
            continue
        comparison = build_comparison(prediction, raw_snapshot)
        if comparison is None:
            continue
        matched_this_run += 1
        by_id[comparison["comparison_id"]] = comparison

    comparisons = sorted(
        by_id.values(),
        key=lambda row: (str(row.get("snapshot_captured_at", "")), str(row.get("race_key", ""))),
    )[-MAX_COMPARISON_ROWS:]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "research_only_ready" if comparisons else "awaiting_matching_pre_race_prediction",
        "verified_market_snapshot_count": sum(
            1 for row in ledger
            if isinstance(row, dict) and normalize_snapshot(row) is not None
        ),
        "comparisons_available": len(comparisons),
        "comparisons_updated_this_run": matched_this_run,
        "comparisons": comparisons,
        "policy": {
            "research_only": True,
            "real_money_authorized": False,
            "does_not_change_no_bet": True,
            "does_not_calculate_roi_from_unsettled_races": True,
            "normalized_market_shares_are_not_true_probabilities": True,
        },
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Live market comparison status: {report['status']}")
    print(f"Research-only comparisons available: {report['comparisons_available']}")
    return report


if __name__ == "__main__":
    main()
