from datetime import date

from src.live.collector import _is_eligible
from src.live.registry import load_manifest
from src.parsers.program_parser import extract_race_info


def test_parser_accepts_non_prix_race_name():
    text = """PARIS-VINCENNES - CRITERIUM DES 5 ANS
15 CONCURRENTS - 4ème COURSE - ATTELE
300 000 EUROS - 2 850 METRES
"""
    race = extract_race_info(text)
    assert race["track"] == "PARIS-VINCENNES"
    assert race["race_name"] == "CRITERIUM DES 5 ANS"
    assert race["runners_count"] == 15


def test_live_validator_rejects_stale_program():
    program = {
        "document_type": "program",
        "date": "2020-01-01",
        "race": {
            "track": "PARISLONGCHAMP",
            "race_number": 1,
            "runners_count": 1,
        },
        "horses": [{"number": 1, "horse": "TEST", "description": ""}],
    }
    eligible, reason = _is_eligible(program, date(2026, 9, 13))
    assert eligible is False
    assert reason == "stale_program"


def test_live_manifest_shape_when_missing():
    payload = load_manifest()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("races"), list)
