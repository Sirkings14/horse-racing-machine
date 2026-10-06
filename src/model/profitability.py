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


def extract_market_odds(prediction: dict[str, Any]) -> dict[int, float]:
    """Read explicit market prices when a source provides them.

    We deliberately do not manufacture odds from model probabilities. A
    profitability claim requires an independently observed market price.
    """
    candidates = [
        prediction.get("market_odds"),
        prediction.get("odds"),
        prediction.get("prices"),
    ]
    ranked = prediction.get("ranked_horses") or []

    for candidate in candidates:
        if isinstance(candidate, dict):
            output: dict[int, float] = {}
            for number, value in candidate.items():
                try:
                    output[int(number)] = float(value)
                except (TypeError, ValueError):
                    continue
            if output:
                return output

    output: dict[int, float] = {}
    for horse in ranked:
        if not isinstance(horse, dict):
            continue
        number = horse.get("horse_number")
        for key in ("market_odds", "odds", "price", "cote"):
            try:
                if number is not None and horse.get(key) is not None:
                    output[int(number)] = float(horse[key])
                    break
            except (TypeError, ValueError):
                continue
    return output


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
        if not isinstance(row, dict) or row.get("observed") is not True:
            continue
        key = (row.get("race_key"), row.get("market_type", "winner"))
        ledger_by_race[key] = row

    for item in evaluations:
        if not isinstance(item, dict):
            continue
        prediction = item.get("prediction") or {}
        odds = extract_market_odds(prediction)
        # Historical evaluation files currently do not preserve market odds.
        # Check the archived prediction separately when available.
        race_key = item.get("race_key")
        archived = {}
        if race_key:
            safe = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in str(race_key))
            archived = load_json(PREDICTIONS_DIR / f"{safe}.json", {})
            if isinstance(archived, dict):
                odds = extract_market_odds(archived) or odds

        # Prefer a separately captured, source-attributed market snapshot.
        snapshot = ledger_by_race.get((race_key, "winner"))
        if snapshot:
            odds = {int(k): float(v) for k, v in (snapshot.get("odds") or {}).items()}
        if not odds:
            continue

        priced_predictions += 1
        recommendations = [int(x) for x in prediction.get("recommended_numbers") or []]
        winner = (item.get("result") or {}).get("winner")
        paper_rows.append({
            "race_key": race_key,
            "accounting": evaluate_fixed_stake(recommendations, winner, odds),
        })

    total_stake = sum(row["accounting"]["stake"] for row in paper_rows)
    total_return = sum(row["accounting"]["return"] for row in paper_rows)
    total_profit = total_return - total_stake

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pricing_ready" if priced_predictions else "awaiting_market_odds",
        "total_verified_predictions": total_predictions,
        "predictions_with_observed_market_odds": priced_predictions,
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
            "observed_snapshot_count": sum(1 for row in ledger if isinstance(row, dict) and row.get("observed") is True),
            "source_attributed_prices_only": True,
        },
        "requirements_for_real_edge_measurement": [
            "capture market odds at prediction time",
            "store the bet type and exact stake rule",
            "store official payout/dividend for the same bet type",
            "calculate ROI and maximum drawdown on chronological out-of-sample predictions",
            "compare model implied probability with independently observed market price",
        ],
        "policy": {
            "never_invent_odds": True,
            "no_profitability_claim_without_observed_prices": True,
            "paper_results_are_not_live_betting_results": True,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Profitability status: {report['status']}")
    print(f"Observed market-price coverage: {report['pricing_coverage']:.1%}")
    return report


if __name__ == "__main__":
    main()
