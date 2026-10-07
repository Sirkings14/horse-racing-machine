from src.model.market_evidence import latest_observed_snapshot, normalize_snapshot


def test_latest_observed_snapshot_prefers_newest_price():
    import src.model.market_evidence as me
    original = me.load_ledger
    me.load_ledger = lambda: [
        normalize_snapshot({"race_key":"r","captured_at":"2026-01-01T10:00:00Z","source":"a","market_type":"winner","odds":{"1":4}}),
        normalize_snapshot({"race_key":"r","captured_at":"2026-01-01T11:00:00Z","source":"a","market_type":"winner","odds":{"1":3}}),
    ]
    try:
        assert latest_observed_snapshot("r")["odds"][1] == 3
    finally:
        me.load_ledger = original
