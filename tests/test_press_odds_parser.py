from src.parsers.program_parser import extract_press_odds
from src.model.economic_validation import evaluate_value_strategy


def test_extracts_published_press_odds_without_confusing_them_with_market_odds():
    text = """
    PARIS TURF
    1 2 3 4
    32/1 15/1 24/1 17/1 29/1 16/1 12/1 8/1 11/1 26/1 97/1 10/1 5/1
    5 6 7 8 9 10 11 12 13
    TIERCE MAGAZINE 35/1 12/1 22/1 15/1 30/1 18/1 10/1 6/1 9/1 27/1 99/1 7/1 3/1
    TURF-FR.COM 12 - 4 - 9 - 5 - 8
    """
    odds = extract_press_odds(text, 13)
    assert set(odds) == {"paris_turf", "tierce_magazine"}
    assert odds["paris_turf"]["1"] == {"fractional": "32/1", "decimal": 33.0}
    assert odds["paris_turf"]["8"]["fractional"] == "8/1"
    assert odds["tierce_magazine"]["13"]["fractional"] == "3/1"
    assert odds["tierce_magazine"]["13"]["decimal"] == 4.0

    # Press prices are intentionally not accepted by the economic gate as
    # operator/market odds. They live under distinct fields.
    result = evaluate_value_strategy([[{
        "probability_winner": 0.5,
        "press_paris_turf_decimal": 33.0,
        "won": 1,
    }]])
    assert result["status"] == "insufficient_price_data"


def test_press_odds_require_a_complete_expected_runner_series():
    text = """
    PARIS TURF 32/1 15/1 24/1
    TIERCE MAGAZINE 35/1 12/1 22/1
    TURF-FR.COM 1 - 2 - 3
    """
    assert extract_press_odds(text, 13) == {}
