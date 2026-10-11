from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.model.market_evidence import load_ledger

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
EVALUATION_FILE = BASE_DIR / "data" / "evaluation" / "prediction_evaluations.json"
OUTPUT_FILE = BASE_DIR / "data" / "evaluation" / "profitability_report.json"
LEDGER_FILE = BASE_DIR / "data" / "evaluation" / "market_evidence.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def evaluate_fixed_stake(
    recommendations: list[int],
    winner: int | None,
    odds: dict[int, float],
    stake_per_selection: float = 1.0,
) -> dict[str, Any]:
    """Simple winner-market paper accounting when actual prices exist."""
    staked = len(recommendations) * stake_per_selection
    returns = 0.0
    winning_selection = None
    if winner in recommendations and winner in odds and odds[winner] > 1:
        winning_selection = winner
        returns = stake_per_selection * odds[winner]

    profit = returns - staked
    return {
        "stake": staked,
        "return": returns,
        "profit": profit,
        "roi": (profit / staked if staked else None),
        "winning_selection": winning_selection,
    }


def _economic_snapshot(row: Any) -> bool:
    """Only strict, timestamped pre-race evidence can enter ROI calculations."""
    if not isinstance(row, dict):
        return False
    if row.get("observed") is not True:
        return False
    if row.get("evidence_grade") != "verified_pre_race_market_odds":
        return False
    if row.get("source_type") not in {"bookmaker_win", "tote_win", "exchange_win"}:
        return False
    if not row.get("source_url") or not row.get("price_timestamp") or not row.get("race_off_at"):
        return False
    try:
        price_time = datetime.fromisoformat(str(row["price_timestamp"]).replace("Z", "+00:00"))
        off_time = datetime.fromisoformat(str(row["race_off_at"]).replace("Z", "+00:00"))
        captured_time = datetime.fromisoformat(str(row["captured_at"]).replace("Z", "+00:00"))
        if any(value.tzinfo is None or value.utcoffset() is None for value in (price_time, off_time, captured_time)):
            return False
        if price_time > captured_time or price_time > off_time or captured_time > off_time:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def main() -> dict[str, Any]:
    evaluations = load_json(EVALUATION_FILE, [])
    if not isinstance(evaluations, list):
        evaluations = []

    total_predictions = len(evaluations)
    priced_predictions = 0
    paper_rows = []
    ledger = load_ledger()
    ledger_by_race = {}
    for row in ledger:
        if not _economic_snapshot(row):
            continue
        key = (row.get("race_key"), row.get("market_type", "winner"))
        previous = ledger_by_race.get(key)
        if previous is None or str(row.get("captured_at", "")) > str(previous.get("captured_at", "")):
            ledger_by_race[key] = row

    for item in evaluations:
        if not isinstance(item, dict):
            continue
        prediction = item.get("prediction") or {}
        race_key = item.get("race_key")
        snapshot = ledger_by_race.get((race_key, "winner"))
        if not snapshot:
            continue

        try:
            odds = {int(k): float(v) for k, v in (snapshot.get("odds") or {}).items()}
        except (TypeError, ValueError):
            continue
        recommendations = [int(x) for x in prediction.get("recommended_numbers") or []]
        # Partial price coverage is not enough to claim a comparable strategy ROI.
        if not recommendations or any(number not in odds or odds[number] <= 1 for number in recommendations):
            continue

        winner_value = (item.get("result") or {}).get("winner")
        try:
            winner = int(winner_value) if winner_value is not None else None
        except (TypeError, ValueError):
            winner = None

        priced_predictions += 1
        accounting = evaluate_fixed_stake(recommendations, winner, odds)
        paper_rows.append({
            "race_key": race_key,
            "source": snapshot.get("source"),
            "source_type": snapshot.get("source_type"),
            "captured_at": snapshot.get("captured_at"),
            "price_timestamp": snapshot.get("price_timestamp"),
            "race_off_at": snapshot.get("race_off_at"),
            "accounting": accounting,
        })

    total_stake = sum(row["accounting"]["stake"] for row in paper_rows)
    total_return = sum(row["accounting"]["return"] for row in paper_rows)
    total_profit = total_return - total_stake

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pricing_ready" if priced_predictions else "awaiting_market_odds",
        "total_verified_predictions": total_predictions,
        "predictions_with_complete_pre_race_market_odds": priced_predictions,
        "pricing_coverage": (priced_predictions / total_predictions if total_predictions else 0.0),
        "paper_accounting": {
            "stake_per_selection": 1.0,
            "total_stake": total_stake,
            "total_return": total_return,
            "total_profit": total_profit,
            "roi": (total_profit / total_stake if total_stake else None),
        },
        "rows": paper_rows,
        "market_evidence": {
            "ledger_path": str(LEDGER_FILE),
            "verified_pre_race_snapshot_count": sum(1 for row in ledger if _economic_snapshot(row)),
            "source_attributed_prices_only": True,
            "complete_recommendation_price_coverage_required": True,
        },
        "requirements_for_real_edge_measurement": [
            "capture actual market odds before the race starts",
            "store source identity, source URL, price timestamp, capture timestamp, and race-off time",
            "store the bet type and exact stake rule",
            "store official payout/dividend for the same bet type",
            "calculate ROI and maximum drawdown on chronological out-of-sample predictions",
            "compare model implied probability with independently observed market price",
        ],
        "policy": {
            "never_invent_odds": True,
            "press_estimates_are_not_market_odds": True,
            "post-race_prices_are_rejected": True,
            "partial_recommendation_price_coverage_is_excluded": True,
            "no_profitability_claim_without_observed_prices": True,
            "paper_results_are_not_live_betting_results": True,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Profitability status: {report['status']}")
    print(f"Verified pre-race market-price coverage: {report['pricing_coverage']:.1%}")
    return report


if __name__ == "__main__":
    main()
