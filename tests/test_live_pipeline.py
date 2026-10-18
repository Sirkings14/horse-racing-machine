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


def test_live_collector_skips_old_dates_encoded_in_pdf_filenames():
    from src.live.collector import _url_is_stale, _url_program_date

    today = date(2026, 10, 18)
    assert _url_program_date("https://example.org/JH_PMUB_DU_14-10-2026.pdf") == date(2026, 10, 14)
    assert _url_is_stale("https://example.org/JH_PMUB_DU_14-10-2026.pdf", today)
    assert _url_is_stale("https://example.org/JH_PMUB_DU_08-10_2026.pdf", today)
    assert not _url_is_stale("https://example.org/JH_PMUB_DU_20-10-2026.pdf", today)
    assert not _url_is_stale("https://example.org/program.pdf", today)


def test_live_collector_reads_iso_dates_from_pdf_filenames():
    from src.live.collector import _url_program_date

    assert _url_program_date("https://example.org/program_2026-10-20.pdf") == date(2026, 10, 20)
