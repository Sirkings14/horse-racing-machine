from src.model.market_evidence import build_unavailable_record, normalize_snapshot


def valid_snapshot(**overrides):
    snapshot = {
        "race_key": "2026-10-12|AUTEUIL|1",
        "captured_at": "2026-10-12T10:00:00+00:00",
        "price_timestamp": "2026-10-12T09:59:30+00:00",
        "race_off_at": "2026-10-12T10:15:00+00:00",
        "source": "example-market",
        "source_type": "bookmaker_win",
        "market_type": "winner",
        "source_url": "https://example.com/race/1",
        "odds": {"1": 4.5, "2": "5.0"},
    }
    snapshot.update(overrides)
    return snapshot


def test_market_evidence_accepts_explicit_pre_race_prices():
    row = normalize_snapshot(valid_snapshot())
    assert row["observed"] is True
    assert row["evidence_grade"] == "verified_pre_race_market_odds"
    assert row["odds"] == {1: 4.5, 2: 5.0}
    assert row["source_type"] == "bookmaker_win"


def test_market_evidence_rejects_missing_provenance_or_invalid_prices():
    assert normalize_snapshot(valid_snapshot(source_url="")) is None
    assert normalize_snapshot(valid_snapshot(source_type="press_estimate")) is None
    assert normalize_snapshot(valid_snapshot(odds={"1": 1.0})) is None
    assert normalize_snapshot(valid_snapshot(odds={})) is None
    assert normalize_snapshot(valid_snapshot(captured_at="not-a-time")) is None
    assert normalize_snapshot(valid_snapshot(price_timestamp="2026-10-12T10:01:00+00:00")) is None


def test_market_evidence_rejects_prices_captured_after_the_race():
    assert normalize_snapshot(valid_snapshot(captured_at="2026-10-12T10:16:00+00:00")) is None


def test_market_evidence_rejects_timestamps_without_timezone():
    assert normalize_snapshot(valid_snapshot(captured_at="2026-10-12T10:00:00")) is None


def test_unavailable_record_cannot_unlock_economic_validation():
    row = build_unavailable_record("2026-10-12|AUTEUIL|1")
    assert row["observed"] is False
    assert row["odds"] == {}
    assert row["policy"]["never_invent_odds"] is True
