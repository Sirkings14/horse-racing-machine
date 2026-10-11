from src.model.v3_discipline_backtest import (
    choose_models,
    discipline_key,
    should_train_specialist,
)


def test_discipline_key_normalizes_french_race_labels():
    assert discipline_key("TROT_ATTELE") == "ATTELE"
    assert discipline_key("TROT MONTE") == "MONTE"
    assert discipline_key("STEEPLE CHASE") == "STEEPLE-CHASE"
    assert discipline_key(None) == "UNKNOWN"


def test_specialist_requires_both_race_and_runner_evidence():
    assert should_train_specialist(300, 3000)
    assert not should_train_specialist(299, 3000)
    assert not should_train_specialist(300, 2999)


def test_unknown_or_data_poor_disciplines_fall_back_to_pooled_model():
    pooled = {"top3": "pooled"}
    specialist = {"PLAT": {"top3": "flat specialist"}}
    chosen, mode = choose_models("PLAT", specialist, pooled)
    assert chosen["top3"] == "flat specialist"
    assert mode == "discipline_specialist"

    chosen, mode = choose_models("UNKNOWN", specialist, pooled)
    assert chosen["top3"] == "pooled"
    assert mode == "pooled_fallback"
