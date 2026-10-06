from src.model.market_evidence import build_unavailable_record, normalize_snapshot

def test_market_evidence_accepts_only_explicit_observed_prices():
    row = normalize_snapshot({
        "race_key": "2026-10-06|AUTEUIL|1",
        "captured_at": "2026-10-06T16:36:52+00:00",
        "source": "test-feed",
        "market_type": "winner",
        "odds": {"3": 4.5, "4": "5.0"},
    })
    assert row["observed"] is True
    assert row["odds"] == {3: 4.5, 4: 5.0}

def test_market_evidence_rejects_inferred_or_invalid_prices():
    assert normalize_snapshot({
        "race_key": "x",
        "captured_at": "now",
        "source": "model",
        "market_type": "winner",
        "odds": {},
    }) is None
    assert normalize_snapshot({
        "race_key": "x",
        "captured_at": "now",
        "source": "model",
        "market_type": "winner",
        "odds": {"1": 1.0},
    }) is None

def test_unavailable_record_cannot_unlock_economic_validation():
    row = build_unavailable_record("2026-10-06|AUTEUIL|1")
    assert row["observed"] is False
    assert row["odds"] == {}
    assert row["policy"]["never_invent_odds"] is True
