import json

from src.dataset.prerace_program_fields import build_program_field_index, merge_program_fields


def test_pre_race_program_join_merges_only_program_fields(tmp_path):
    programs = tmp_path / "programs"
    programs.mkdir()
    payload = {
        "date": "2026-01-02",
        "race": {"track": "SAINT-CLOUD", "race_number": 1},
        "program_table_mapping_status": "mapped",
        "horses": [
            {
                "number": 7,
                "horse": "CHEVAL TEST",
                "trainer": "T.ONE",
                "driver": "D.ONE",
                "jockey": "D.ONE",
                "weight": 58,
                "draw": 4,
            }
        ],
    }
    (programs / "race.json").write_text(json.dumps(payload), encoding="utf-8")
    index = build_program_field_index(programs)
    rows = [{
        "date": "2026-01-02",
        "track": "SAINT-CLOUD",
        "race_number": 1,
        "horse_number": 7,
        "horse_name": "Cheval Test",
        "finish_position": 1,
        "won": 1,
    }]
    matched, ambiguous = merge_program_fields(rows, index)
    assert (matched, ambiguous) == (1, 0)
    assert rows[0]["trainer"] == "T.ONE"
    assert rows[0]["driver"] == "D.ONE"
    assert rows[0]["finish_position"] == 1
    assert rows[0]["won"] == 1


def test_ambiguous_program_matches_fail_closed(tmp_path):
    programs = tmp_path / "programs"
    programs.mkdir()
    for i, track in enumerate(("SAINT-CLOUD", "CHANTILLY"), 1):
        payload = {
            "date": "2026-01-02",
            "race": {"track": track, "race_number": i},
            "program_table_mapping_status": "mapped",
            "horses": [{"number": 7, "horse": "CHEVAL TEST", "trainer": f"T.{i}", "driver": f"D.{i}"}],
        }
        (programs / f"race{i}.json").write_text(json.dumps(payload), encoding="utf-8")
    index = build_program_field_index(programs)
    rows = [{
        "date": "2026-01-02",
        "track": None,
        "race_number": None,
        "horse_number": 7,
        "horse_name": "CHEVAL TEST",
    }]
    matched, ambiguous = merge_program_fields(rows, index)
    assert matched == 0
    assert ambiguous == 1
    assert "trainer" not in rows[0]
