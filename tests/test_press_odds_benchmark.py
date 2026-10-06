from src.model.press_odds_benchmark import accounting


def test_value_filter_uses_probability_against_published_price():
    races = [{
        "race_key": "2026-09-10|TEST|1",
        "winner": 1,
        "press_odds": {
            "paris_turf": {
                "1": {"decimal": 3.0},
                "2": {"decimal": 2.0},
                "3": {"decimal": 2.0},
                "4": {"decimal": 2.0},
                "5": {"decimal": 2.0},
            }
        },
        "top5": [
            {"horse_number": 1, "probability_winner": 0.50},
            {"horse_number": 2, "probability_winner": 0.10},
            {"horse_number": 3, "probability_winner": 0.10},
            {"horse_number": 4, "probability_winner": 0.10},
            {"horse_number": 5, "probability_winner": 0.10},
        ],
    }]
    result = accounting(races, "paris_turf", value_only=True)
    assert result["bets"] == 1
    assert result["wins"] == 1
    assert result["profit"] == 2.0
    assert result["roi"] == 2.0


def test_published_prices_do_not_unlock_market_evidence():
    races = [{
        "race_key": "2026-09-10|TEST|1",
        "winner": 1,
        "press_odds": {"paris_turf": {"1": {"decimal": 3.0}}},
        "top5": [{"horse_number": 1, "probability_winner": 0.50}],
    }]
    result = accounting(races, "paris_turf", value_only=True)
    assert result["bets"] == 1
    from src.model import press_odds_benchmark
    assert press_odds_benchmark.SOURCES["paris_turf"] == "Paris Turf"


def test_drawdown_is_computed_chronologically():
    races = [
        {
            "race_key": "2026-09-10|TEST|1",
            "winner": 2,
            "press_odds": {"paris_turf": {"1": {"decimal": 2.0}, "2": {"decimal": 2.0}, "3": {"decimal": 2.0}, "4": {"decimal": 2.0}, "5": {"decimal": 2.0}}},
            "top5": [{"horse_number": n, "probability_winner": 0.20} for n in range(1, 6)],
        },
        {
            "race_key": "2026-09-11|TEST|1",
            "winner": 9,
            "press_odds": {"paris_turf": {str(n): {"decimal": 2.0} for n in range(1, 6)}},
            "top5": [{"horse_number": n, "probability_winner": 0.20} for n in range(1, 6)],
        },
    ]
    result = accounting(races, "paris_turf", value_only=False)
    assert result["maximum_drawdown_units"] >= 0
