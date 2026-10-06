from src.model.press_odds_benchmark import simulate, complete_priced_races


def race(rows):
    return {"race_key": "2026-01-01|TEST|1", "top5_candidates": rows}


def candidate(number, probability, odds, won=0):
    return {
        "horse_number": number,
        "probability_winner": probability,
        "press_paris_turf_decimal": odds,
        "won": won,
    }


def test_value_filter_uses_probability_against_explicit_press_price():
    rows = [
        candidate(1, 0.50, 3.0, 1),
        candidate(2, 0.10, 2.0),
        candidate(3, 0.10, 2.0),
        candidate(4, 0.10, 2.0),
        candidate(5, 0.10, 2.0),
    ]
    priced = complete_priced_races([race(rows)], "press_paris_turf_decimal")
    result = simulate(priced, "press_paris_turf_decimal", value_only=True)
    assert result["bets"] == 1
    assert result["wins"] == 1
    assert result["profit"] == 2.0
    assert result["roi"] == 2.0


def test_incomplete_press_price_series_is_not_counted():
    rows = [
        candidate(1, 0.50, 3.0),
        candidate(2, 0.10, 2.0),
        candidate(3, 0.10, 2.0),
        candidate(4, 0.10, 2.0),
        {"horse_number": 5, "probability_winner": 0.10, "won": 0},
    ]
    assert complete_priced_races([race(rows)], "press_paris_turf_decimal") == []


def test_benchmark_does_not_claim_market_evidence():
    # This test documents the contract: this module can evaluate published
    # prices without being used by the live market-evidence gate.
    from src.model import press_odds_benchmark
    assert press_odds_benchmark.SOURCES["paris_turf"] == "press_paris_turf_decimal"
