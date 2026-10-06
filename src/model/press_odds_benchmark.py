from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
BACKTEST_FILE = BASE_DIR / "data" / "model" / "v3_backtest_report.json"
OUTPUT_FILE = BASE_DIR / "data" / "model" / "press_odds_benchmark_report.json"

SOURCES = {
    "paris_turf": "press_paris_turf_decimal",
    "tierce_magazine": "press_tierce_magazine_decimal",
}
EDGE_THRESHOLD = 0.08


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def safe_odds(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 1.0 else None


def safe_probability(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


def race_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("race_results")
    return rows if isinstance(rows, list) else []


def candidate_rows(race: dict[str, Any]) -> list[dict[str, Any]]:
    rows = race.get("top5_candidates")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def complete_priced_races(races: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    priced = []
    for race in races:
        candidates = candidate_rows(race)
        if len(candidates) < 5:
            continue
        if all(safe_odds(row.get(field)) is not None for row in candidates[:5]):
            priced.append(race)
    return priced


def simulate(races: list[dict[str, Any]], field: str, value_only: bool) -> dict[str, Any]:
    bets = 0
    wins = 0
    stake = 0.0
    returned = 0.0
    edges: list[float] = []
    per_race = []

    for race in races:
        candidates = candidate_rows(race)[:5]
        race_bets = 0
        race_return = 0.0
        race_stake = 0.0
        race_edges: list[float] = []
        selected = []

        for row in candidates:
            odds = safe_float(row.get(field))
            probability = safe_probability(row.get("probability_winner"))
            if odds is None or probability is None:
                continue
            probability_edge = probability - (1.0 / odds)
            if value_only and probability_edge < EDGE_THRESHOLD:
                continue

            selected.append(int(row.get("horse_number")))
            race_bets += 1
            race_stake += 1.0
            bets += 1
            stake += 1.0
            edges.append(probability_edge)
            race_edges.append(probability_edge)

            won = int(row.get("won", 0)) == 1
            if won:
                wins += 1
                returned += odds
                race_return += odds

        # Preserve only compact chronological accounting needed for drawdown.
        per_race.append({
            "race_key": race.get("race_key"),
            "selected": selected,
            "stake": race_stake,
            "return": race_return,
            "profit": race_return - race_stake,
            "max_edge": max(race_edges) if race_edges else None,
        })

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in per_race:
        equity += float(row["profit"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    profit = returned - stake
    return {
        "bets": bets,
        "wins": wins,
        "win_rate": round(wins / bets, 4) if bets else None,
        "total_stake": round(stake, 4),
        "total_return": round(returned, 4),
        "profit": round(profit, 4),
        "roi": round(profit / stake, 4) if stake else None,
        "average_probability_edge": round(sum(edges) / len(edges), 4) if edges else None,
        "maximum_drawdown_units": round(max_drawdown, 4),
        "race_accounting": per_race,
    }


def build_report() -> dict[str, Any]:
    source = load_json(BACKTEST_FILE, {})
    if not isinstance(source, dict):
        source = {}
    races = race_rows(source)
    evaluated = len(races)

    sources: dict[str, Any] = {}
    for source_name, field in SOURCES.items():
        priced = complete_priced_races(races, field)
        all_top5 = simulate(priced, field, value_only=False)
        value_only = simulate(priced, field, value_only=True)
        sources[source_name] = {
            "price_field": field,
            "priced_races": len(priced),
            "priced_race_coverage": round(len(priced) / evaluated, 4) if evaluated else 0.0,
            "top5_selection_accounting": {k: v for k, v in all_top5.items() if k != "race_accounting"},
            "value_filtered_accounting": {k: v for k, v in value_only.items() if k != "race_accounting"},
            "value_threshold_probability_edge": EDGE_THRESHOLD,
            "chronological_race_accounting": value_only["race_accounting"],
        }

    report = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "benchmark_available" if evaluated else "no_backtest_data",
        "method": "chronological_v4_holdout_press_price_benchmark",
        "source_backtest": str(BACKTEST_FILE),
        "evaluated_races": evaluated,
        "press_prices_are_market_evidence": False,
        "market_evidence_gate_unlocked": False,
        "policy": {
            "press_publications_are_benchmark_only": True,
            "operator_or_tote_prices_required_for_live_economic_validation": True,
            "never_invent_market_odds": True,
            "prediction_time_alignment_exact_timestamp_unavailable": True,
        },
        "sources": sources,
        "interpretation": {
            "probability_edge": "model probability_winner minus 1/press_decimal_odds",
            "positive_ev_filter": "probability_edge >= 0.08",
            "flat_stake_unit": 1.0,
            "paper_accounting_only": True,
        },
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> dict[str, Any]:
    report = build_report()
    print(json.dumps({
        "status": report["status"],
        "evaluated_races": report["evaluated_races"],
        "sources": {
            name: {
                "priced_races": value["priced_races"],
                "top5_roi": value["top5_selection_accounting"]["roi"],
                "value_filtered_bets": value["value_filtered_accounting"]["bets"],
                "value_filtered_roi": value["value_filtered_accounting"]["roi"],
            }
            for name, value in report["sources"].items()
        },
        "market_evidence_gate_unlocked": report["market_evidence_gate_unlocked"],
    }, indent=2))
    return report


if __name__ == "__main__":
    main()
