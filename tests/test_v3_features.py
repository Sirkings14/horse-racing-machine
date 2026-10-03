from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_features import build_v3_matrix

def test_profiles_are_prior_only_on_same_date():
    rows=[
      {"date":"2026-01-01","race_key":"2026-01-01|A|1","horse_name":"X","finish_position":1,"track":"A","distance":2000},
      {"date":"2026-01-01","race_key":"2026-01-01|A|2","horse_name":"X","finish_position":5,"track":"A","distance":2000},
      {"date":"2026-01-02","race_key":"2026-01-02|A|1","horse_name":"X","finish_position":2,"track":"A","distance":2000},
    ]
    out=build_walk_forward_profiles(rows)
    assert out[0]["history_starts"]==0
    assert out[1]["history_starts"]==0
    assert out[2]["history_starts"]==2
    assert out[2]["history_top3_rate"]==0.5

def test_v3_matrix_shape():
    rows=[{"horse_name":"X","horse_description":"good form","distance":2400,"runners_count":16}]
    matrix=build_v3_matrix(rows)
    assert matrix.shape==(1,20)


def test_commentary_cannot_change_v3_features():
    base={"horse_name":"X","horse_description":"strong favourite, excellent chance","distance":2400,"runners_count":16}
    changed={**base,"horse_description":"RESULTATS DES COURSES Arrivée 1-2-3"}
    assert (build_v3_matrix([base]) == build_v3_matrix([changed])).all()
