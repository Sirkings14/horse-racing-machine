from src.model.economic_validation import evaluate_value_strategy

def test_economic_gate_refuses_missing_prices():
    result=evaluate_value_strategy([[{"probability_winner":0.5,"won":1}]])
    assert result["status"]=="insufficient_price_data"

def test_economic_gate_uses_only_explicit_price():
    result=evaluate_value_strategy([[{"probability_winner":0.5,"win_odds_decimal":3.0,"won":1}]])
    assert result["status"]=="available"
    assert result["bets"]==1
    assert result["profit_flat_stake"]==2.0

def test_economic_gate_does_not_use_ensemble_score_as_probability():
    # Ensemble ranking score is not a win probability. With 0.50 win
    # probability at 3.0 odds, edge is positive; with ensemble_score 0.99
    # alone, it must not create a fabricated value bet.
    result=evaluate_value_strategy([[
        {"ensemble_score":0.99,"win_odds_decimal":3.0,"won":0}
    ]])
    assert result["status"]=="insufficient_price_data"
    assert result["bets"]==0
