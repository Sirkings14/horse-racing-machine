from src.model.historical_profile import build_walk_forward_profiles
from src.model.v3_features import build_v3_matrix, FEATURE_NAMES
import json
import src.dataset.program_history as program_history

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
    assert out[2]["course_top5_rate"]==1.0
    assert out[2]["distance_top3_rate"]==0.5

def test_v3_matrix_shape():
    rows=[{"horse_name":"X","horse_description":"good form","distance":2400,"runners_count":16}]
    matrix=build_v3_matrix(rows)
    assert matrix.shape==(1,len(FEATURE_NAMES))

def test_invalid_distance_is_unknown_not_real_distance():
    valid=build_v3_matrix([{"horse_name":"X","distance":2400,"runners_count":16}])[0]
    invalid=build_v3_matrix([{"horse_name":"X","distance":100,"runners_count":16}])[0]
    assert valid[15]>0 and valid[16]==1.0
    assert invalid[15]==0.0 and invalid[16]==0.0

def test_commentary_cannot_change_v3_features():
    base={"horse_name":"X","horse_description":"strong favourite, excellent chance","distance":2400,"runners_count":16}
    changed={**base,"horse_description":"RESULTATS DES COURSES Arrivée 1-2-3"}
    assert (build_v3_matrix([base]) == build_v3_matrix([changed])).all()


def test_race_relative_features_change_only_from_pre_race_batch():
    rows=[
      {"horse_name":"A","history_win_rate":0.8,"history_top3_rate":0.8,"history_top5_rate":0.9,"history_recent_top3_rate":0.8,"history_recent_top5_rate":0.9,"history_recent_avg_finish":2,"course_top3_rate":0.8,"distance_top3_rate":0.8,"history_starts":10,"distance":2400,"runners_count":10},
      {"horse_name":"B","history_win_rate":0.2,"history_top3_rate":0.2,"history_top5_rate":0.3,"history_recent_top3_rate":0.2,"history_recent_top5_rate":0.3,"history_recent_avg_finish":7,"course_top3_rate":0.2,"distance_top3_rate":0.2,"history_starts":2,"distance":2400,"runners_count":10},
    ]
    matrix=build_v3_matrix(rows)
    assert matrix.shape==(2,len(FEATURE_NAMES))
    assert matrix[0,-1] > matrix[1,-1]


def test_walk_forward_profiles_expose_live_data_completeness():
    rows=[{
        "date":"2026-10-07","race_key":"2026-10-07|ENGHIEN|1","track":"ENGHIEN",
        "distance":2875,"runners_count":18,"horse_number":15,"horse_name":"IXELLE BLEUE"
    }]
    out=build_walk_forward_profiles(rows)
    assert out[0]["data_completeness"]==1.0

def test_program_only_start_counts_as_experience_without_fake_result():
    rows=[
      {"date":"2026-01-01","race_key":"2026-01-01|A|1","horse_name":"X","finish_position":None,"track":"A","distance":2000},
      {"date":"2026-01-02","race_key":"2026-01-02|A|1","horse_name":"X","finish_position":2,"track":"A","distance":2000},
    ]
    out=build_walk_forward_profiles(rows)
    assert out[1]["history_starts"]==1
    assert out[1]["history_top3_rate"]==0.0
    assert out[1]["course_starts"]==1
    assert out[1]["course_top3_rate"]==0.0
    assert out[1]["distance_starts"]==1
    assert out[1]["distance_top3_rate"]==0.0
    assert out[1]["days_since_last_run"]==1


def test_program_history_loader_excludes_cutoff_and_has_no_targets(tmp_path, monkeypatch):
    payload={
      "date":"2026-01-01",
      "race":{"track":"A","race_number":1,"race_name":"R","race_type":"PLAT","distance":2000,"runners_count":2},
      "horses":[{"number":1,"horse":"X","description":""},{"number":2,"horse":"Y","description":""}],
    }
    path=tmp_path/"race.json"
    path.write_text(json.dumps(payload),encoding="utf-8")
    monkeypatch.setattr(program_history,"PROGRAMS_DIR",tmp_path)
    rows=program_history.load_program_history("2026-01-02")
    assert len(rows)==2
    assert all(r["_program_only_history"] is True for r in rows)
    assert all("won" not in r and "finish_position" not in r for r in rows)
    assert program_history.load_program_history("2026-01-01")==[]
