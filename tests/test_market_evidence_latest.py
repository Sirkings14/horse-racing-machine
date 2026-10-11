from src.model.market_evidence import latest_observed_snapshot, normalize_snapshot


def _valid_snapshot(captured_at: str, price_timestamp: str, odds: float) -> dict:
    return {
        "race_key": "2026-01-01|AUTEUIL|1",
        "captured_at": captured_at,
        "price_timestamp": price_timestamp,
        "race_off_at": "2026-01-01T12:00:00Z",
        "source": "example-market",
        "source_type": "bookmaker_win",
        "market_type": "winner",
        "source_url": "https://example.com/race/1",
        "odds": {"1": odds},
    }


def test_latest_observed_snapshot_prefers_newest_price():
    import src.model.market_evidence as me

    original = me.load_ledger
    me.load_ledger = lambda: [
        normalize_snapshot(
            _valid_snapshot(
                "2026-01-01T10:00:00Z",
                "2026-01-01T09:59:30Z",
                4.0,
            )
        ),
        normalize_snapshot(
            _valid_snapshot(
                "2026-01-01T11:00:00Z",
                "2026-01-01T10:59:30Z",
                3.0,
            )
        ),
    ]
    try:
        latest = latest_observed_snapshot("2026-01-01|AUTEUIL|1")
        assert latest is not None
        assert latest["odds"][1] == 3.0
    finally:
        me.load_ledger = original
