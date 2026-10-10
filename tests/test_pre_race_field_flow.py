from src.dataset.build_dataset import extract_race_rows
from src.model.predict_v3 import _live_rows
from src.parsers.program_parser import extract_race_info


def test_historical_row_preserves_validated_pre_race_program_fields():
    program = {
        "date": "2026-01-02",
        "race": {
            "track": "VINCENNES", "race_number": 1, "race_name": "TEST",
            "race_type": "TROT MONTÉ", "distance": 2700,
            "runners_count": 1, "prize_euros": 50000, "going": "SOUPLE", "surface": "HERBE", "start_method": "AUTOSTART",
        },
        "horses": [{
            "number": 7, "horse": "HORSE A", "sex": "H", "age": 6,
            "weight": 62.0, "draw": 4, "performance": "1.2.D.3.4",
            "gains": 75000, "listed_chrono": "1.12.3",
            "listed_distance": "2700.M", "trainer": "TRAINER A",
            "jockey": "JOCKEY A", "driver": "DRIVER A", "owner": "OWNER A",
        }],
    }
    record = {
        "program": program,
        "result": {"date": "2026-01-02", "track": "VINCENNES", "race_number": 1, "arrival": [7]},
        "match": {"status": "MATCHED"},
    }

    rows = extract_race_rows(record)
    assert len(rows) == 1
    row = rows[0]
    assert row["race_type"] == "MONTE"
    assert row["performance"] == "1.2.D.3.4"
    assert row["gains"] == 75000.0
    assert row["listed_chrono"] == "1.12.3"
    assert row["sex"] == "H"
    assert row["age"] == 6
    assert row["trainer"] == "TRAINER A"
    assert row["driver"] == "DRIVER A"
    assert row["going"] == "SOUPLE"
    assert row["surface"] == "HERBE"
    assert row["start_method"] == "AUTOSTART"


def test_live_row_preserves_same_pre_race_fields_as_historical_row():
    program = {
        "date": "2026-10-11",
        "race": {
            "track": "VINCENNES", "race_number": 1, "race_name": "TEST",
            "race_type": "MONTÉ", "distance": 2700, "runners_count": 1,
            "prize_euros": 50000,
        },
        "horses": [{
            "number": 7, "horse": "HORSE A", "sex": "H", "age": 6,
            "weight": 62.0, "draw": 4, "performance": "1.2.D.3.4",
            "gains": 75000, "listed_chrono": "1.12.3",
            "listed_distance": "2700.M", "trainer": "TRAINER A",
            "jockey": "JOCKEY A", "driver": "DRIVER A", "owner": "OWNER A",
        }],
    }
    rows = _live_rows(program)
    assert len(rows) == 1
    assert rows[0]["race_type"] == "MONTE"
    assert rows[0]["going"] == "SOUPLE"
    assert rows[0]["surface"] == "HERBE"
    assert rows[0]["start_method"] == "AUTOSTART"
    for field in ("performance", "gains", "listed_chrono", "listed_distance", "sex", "age", "trainer", "driver"):
        assert rows[0][field] == program["horses"][0][field]


def test_program_parser_normalizes_mounted_trot_accent():
    info = extract_race_info("MONTÉ 2700 METRES")
    assert info["race_type"] == "MONTE"
