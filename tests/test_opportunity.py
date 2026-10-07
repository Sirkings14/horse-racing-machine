from src.model.opportunity import score_race_opportunity


def test_race_quality_is_separate_from_profitability():
    ranked = [
        {"horse_number": 1, "probability_winner": .30, "probability_top3": .60, "probability_top5": .80,
         "ensemble_score": .50, "model_disagreement": .02, "data_completeness": 1.0},
        {"horse_number": 2, "probability_winner": .20, "probability_top3": .45, "probability_top5": .65,
         "ensemble_score": .44, "model_disagreement": .03, "data_completeness": 1.0},
        {"horse_number": 3, "probability_winner": .10, "probability_top3": .30, "probability_top5": .50,
         "ensemble_score": .35, "model_disagreement": .04, "data_completeness": 1.0},
    ]
    out = score_race_opportunity(ranked)
    assert out["tier"] in {"A", "B", "C", "D"}
    assert out["market_edge_available"] is False
    assert out["value_candidates"] == []


def test_only_observed_market_prices_create_value_candidates():
    ranked = [
        {"horse_number": 1, "probability_winner": .40, "probability_top3": .70, "probability_top5": .90,
         "ensemble_score": .60, "model_disagreement": .02, "data_completeness": 1.0},
        {"horse_number": 2, "probability_winner": .15, "probability_top3": .35, "probability_top5": .60,
         "ensemble_score": .40, "model_disagreement": .03, "data_completeness": 1.0},
    ]
    out = score_race_opportunity(ranked, {1: 3.0, 2: 5.0})
    assert out["market_edge_available"] is True
    assert out["value_candidates"][0]["horse_number"] == 1
    assert out["value_candidates"][0]["edge"] > 0
