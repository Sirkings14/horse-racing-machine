from src.model.economic_validation import evaluate_value_strategy

def test_economic_gate_refuses_missing_prices():
    result=evaluate_value_strategy([[{"ensemble_score":0.5,"won":1}]])
    assert result["status"]=="insufficient_price_data"

def test_economic_gate_uses_only_explicit_price():
    result=evaluate_value_strategy([[{"ensemble_score":0.5,"win_odds_decimal":3.0,"won":1}]])
    assert result["status"]=="available"
    assert result["bets"]==1
    assert result["profit_flat_stake"]==2.0
