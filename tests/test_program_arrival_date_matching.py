from src.parsers.program_parser import extract_published_arrival


def test_future_program_ignores_arrival_from_previous_day():
    text = "PROGRAMME DU LUNDI 12 OCTOBRE 2026\nARRIVEE DU DIMANCHE 11 OCTOBRE 2026 : 9-10-4"
    assert extract_published_arrival(text, "2026-10-12") == []


def test_same_day_published_arrival_is_preserved():
    text = "PROGRAMME DU DIMANCHE 11 OCTOBRE 2026\nARRIVEE DU DIMANCHE 11 OCTOBRE 2026 : 8-13-12-7-4"
    assert extract_published_arrival(text, "2026-10-11") == [8, 13, 12, 7, 4]


def test_undated_arrival_is_not_attached_to_a_race():
    text = "PROGRAMME DU LUNDI 12 OCTOBRE 2026\nARRIVEE DU : 9-10-4"
    assert extract_published_arrival(text, "2026-10-12") == []


def test_arrival_heading_without_year_uses_program_year_but_still_checks_day():
    text = "ARRIVEE DU DIMANCHE 11 OCTOBRE : 8-13-12"
    assert extract_published_arrival(text, "2026-10-11") == [8, 13, 12]
    assert extract_published_arrival(text, "2026-10-12") == []
