from src.model.historical_profile import build_walk_forward_profiles, horse_identity_source

def test_stable_horse_id_is_preferred_over_name():
    rows = [
        {"date":"2026-01-01","race_key":"A","horse_name":"SAME NAME","horse_id":"H1","finish_position":1,"track":"A","distance":2000},
        {"date":"2026-01-02","race_key":"B","horse_name":"SAME NAME","horse_id":"H2","finish_position":1,"track":"A","distance":2000},
        {"date":"2026-01-03","race_key":"C","horse_name":"SAME NAME","horse_id":"H1","finish_position":3,"track":"A","distance":2000},
    ]
    out = build_walk_forward_profiles(rows)
    assert out[0]["history_starts"] == 0
    assert out[1]["history_starts"] == 0
    assert out[2]["history_starts"] == 1
    assert out[2]["history_win_rate"] == 1.0
    assert all(horse_identity_source(row) == "stable_id" for row in rows)

def test_name_fallback_normalizes_accents_and_punctuation():
    rows = [
        {"date":"2026-01-01","race_key":"A","horse_name":"Étoile-d'Or","finish_position":2,"track":"A","distance":2000},
        {"date":"2026-01-02","race_key":"B","horse_name":"ETOILE D OR","finish_position":4,"track":"A","distance":2000},
    ]
    out = build_walk_forward_profiles(rows)
    assert out[1]["history_starts"] == 1
    assert out[1]["history_top3_rate"] == 1.0
    assert out[1]["horse_identity_source"] == "normalized_name"
