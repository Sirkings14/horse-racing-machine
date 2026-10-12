from datetime import date, datetime, timezone

from src.model.live_pmu_odds_capture import (
    MAX_LOOKAHEAD_MINUTES,
    _participants_url,
    build_snapshot,
    course_matches_program,
    iter_pmu_courses,
    match_pmu_course,
    summarize_participant_schema,
)
from src.model.market_evidence import normalize_snapshot


def _program():
    return {
        "document_type": "program",
        "date": "2026-10-12",
        "race": {
            "track": "MARSEILLE-BORELY",
            "race_number": 4,
            "race_name": "PRIX JACQUES ROSSI",
            "distance": 2100,
            "runners_count": 5,
        },
        "horses": [
            {"number": 1, "horse": "BAYAMOON"},
            {"number": 2, "horse": "WINDFLOWER"},
            {"number": 3, "horse": "MORPHEWAN"},
            {"number": 4, "horse": "PLATA D OCTOBRE"},
            {"number": 5, "horse": "LINFASOMMER"},
        ],
    }


def _daily_program(include_date=True):
    payload = {
        "date": "2026-10-12",
        "reunions": [
            {
                "numOfficiel": 3,
                "hippodrome": {"libelleLong": "MARSEILLE BORELY"},
                "courses": [
                    {
                        "numExterne": 4,
                        "libelle": "PRIX JACQUES ROSSI",
                        "heureDepart": "14:04:00",
                        "distance": 2100,
                        "nombrePartants": 5,
                    }
                ],
            }
        ],
    }
    if not include_date:
        payload.pop("date", None)
    return payload


def _participants():
    names = ["BAYAMOON", "WINDFLOWER", "MORPHEWAN", "PLATA D OCTOBRE", "LINFASOMMER"]
    return {
        "participants": [
            {
                "numPmu": index,
                "nom": name,
                "statut": "PARTANT",
                "cotes": [{
                    "typePari": "SIMPLE_GAGNANT",
                    "cote": float(index + 2),
                    "dateCote": "2026-10-12T13:59:00+02:00",
                }],
            }
            for index, name in enumerate(names, 1)
        ]
    }


def test_daily_program_adapter_inherits_venue_and_meeting_number():
    courses = iter_pmu_courses(_daily_program())
    assert len(courses) == 1
    assert courses[0]["track"] == "MARSEILLE BORELY"
    assert courses[0]["meeting_number"] == 3
    assert courses[0]["course_number"] == 4
    assert courses[0]["distance"] == 2100
    assert courses[0]["runners_count"] == 5


def test_time_only_off_is_parsed_when_daily_payload_omits_date():
    courses = iter_pmu_courses(_daily_program(include_date=False), race_date="2026-10-12")
    assert len(courses) == 1
    assert courses[0]["off_at"] == datetime(2026, 10, 12, 12, 4, tzinfo=timezone.utc)


def test_race_matching_requires_venue_name_distance_and_field_size():
    course = iter_pmu_courses(_daily_program())[0]
    program = _program()
    assert course_matches_program(course, program)
    assert match_pmu_course([course], program) == course

    # PMU prefixes its venue with "HIPPODROME DE"; it must still match the
    # shortened canonical LONAB venue when every other field agrees.
    pmu_venue = dict(course, track="HIPPODROME DE MARSEILLE BORELY")
    assert course_matches_program(pmu_venue, program)
    assert match_pmu_course([pmu_venue], program) == pmu_venue

    wrong_venue = dict(course, track="CHANTILLY")
    wrong_distance = dict(course, distance=1800)
    wrong_name = dict(course, race_name="PRIX SANS RAPPORT")
    assert not course_matches_program(wrong_venue, program)
    assert not course_matches_program(wrong_distance, program)
    assert not course_matches_program(wrong_name, program)
    assert match_pmu_course([course, dict(course, meeting_number=4)], program) is None


def test_participant_url_uses_confirmed_meeting_and_course_ids():
    url = _participants_url(date(2026, 10, 12), 3, 4)
    assert url.endswith("/programme/12102026/R3/C4/participants?specialisation=INTERNET")


def test_build_snapshot_preserves_direct_win_prices_and_runner_quote_times():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    snapshot = build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4",
        _program(),
        course,
        _participants(),
        now,
    )
    assert snapshot is not None
    assert snapshot["source_type"] == "tote_win"
    assert snapshot["market_type"] == "winner"
    assert snapshot["odds"] == {"1": 3.0, "2": 4.0, "3": 5.0, "4": 6.0, "5": 7.0}
    assert snapshot["runner_price_timestamps"]["1"] == "2026-10-12T11:59:00+00:00"
    normalized = normalize_snapshot(snapshot)
    assert normalized is not None
    assert normalized["evidence_grade"] == "verified_pre_race_market_odds"
    assert normalized["runner_price_timestamps"][1] == "2026-10-12T11:59:00+00:00"


def test_build_snapshot_accepts_timestamped_direct_win_quotes():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    payload = _participants()
    for index, participant in enumerate(payload["participants"], 1):
        participant.pop("cotes", None)
        participant["dernierRapportDirect"] = {
            "typePari": "SIMPLE_GAGNANT",
            "typeRapport": "PROBABLE",
            "rapport": float(index + 2),
            "dateRapport": "2026-10-12T13:59:00+02:00",
        }
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    snapshot = build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4", _program(), course, payload, now
    )
    assert snapshot is not None
    assert snapshot["odds"] == {"1": 3.0, "2": 4.0, "3": 5.0, "4": 6.0, "5": 7.0}
    assert snapshot["runner_price_timestamps"]["1"] == "2026-10-12T11:59:00+00:00"


def test_build_snapshot_accepts_pmu_e_simple_gagnant_label_with_epoch_timestamp():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    payload = _participants()
    for index, participant in enumerate(payload["participants"], 1):
        participant.pop("cotes", None)
        participant["dernierRapportDirect"] = {
            "typePari": "E_SIMPLE_GAGNANT",
            "typeRapport": "DIRECT",
            "rapport": float(index + 2),
            "dateRapport": 1791806340000,
        }

    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    snapshot = build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4", _program(), course, payload, now
    )

    assert snapshot is not None
    assert snapshot["odds"] == {"1": 3.0, "2": 4.0, "3": 5.0, "4": 6.0, "5": 7.0}
    assert snapshot["runner_price_timestamps"]["1"] == "2026-10-12T11:59:00+00:00"


def test_untyped_generic_report_is_not_accepted_as_a_live_odds_quote():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    payload = _participants()
    for participant in payload["participants"]:
        participant.pop("cotes", None)
        participant["dernierRapportDirect"] = {
            "rapport": 3.4,
            "dateRapport": "2026-10-12T13:59:00+02:00",
        }
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    assert build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4", _program(), course, payload, now
    ) is None


def test_quote_schema_diagnostic_reports_shape_without_price_values():
    program = _program()
    payload = _participants()
    diagnostic = summarize_participant_schema(program, payload)

    assert diagnostic["participant_count"] == 5
    assert diagnostic["program_runner_count"] == 5
    assert diagnostic["identity_matches"] == 5
    assert diagnostic["explicit_cote_field_count"] == 0
    assert diagnostic["runner_samples_without_price_values"][0]["cotes"]["sample_items"][0]["typePari"] == "SIMPLE_GAGNANT"
    assert "rapport" not in diagnostic["runner_samples_without_price_values"][0]


def test_quote_schema_diagnostic_counts_typed_direct_quotes_and_timestamps():
    program = _program()
    payload = _participants()
    for index, participant in enumerate(payload["participants"], 1):
        participant.pop("cotes", None)
        participant["dernierRapportDirect"] = {
            "typePari": "SIMPLE_GAGNANT",
            "typeRapport": "PROBABLE",
            "rapport": float(index + 2),
            "dateRapport": "2026-10-12T13:59:00+02:00",
        }

    diagnostic = summarize_participant_schema(program, payload)
    assert diagnostic["direct_report_dict_count"] == 5
    assert diagnostic["direct_report_win_type_count"] == 5
    assert diagnostic["direct_report_positive_numeric_count"] == 5
    assert diagnostic["direct_report_timestamp_present_count"] == 5
    assert diagnostic["runner_samples_without_price_values"][0]["direct_quote"]["rapport_positive_numeric"] is True
    assert diagnostic["runner_samples_without_price_values"][0]["direct_quote"]["timestamp_parseable"] is True


def test_no_snapshot_is_built_at_or_after_scheduled_off_time():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    after_off = datetime(2026, 10, 12, 12, 5, tzinfo=timezone.utc)
    assert build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4",
        _program(),
        course,
        _participants(),
        after_off,
    ) is None


def test_unknown_or_low_coverage_runner_data_fails_closed():
    course = iter_pmu_courses(_daily_program())[0]
    course["participants_url"] = _participants_url(date(2026, 10, 12), 3, 4)
    participants = _participants()
    participants["participants"][0]["nom"] = "WRONG HORSE"
    participants["participants"][1]["cotes"][0]["cote"] = 0
    participants["participants"][2]["cotes"][0]["typePari"] = "TRIO"
    participants["participants"][3]["statut"] = "NON_PARTANT"
    assert build_snapshot(
        "2026-10-12|MARSEILLE-BORELY|4",
        _program(),
        course,
        participants,
        datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
    ) is None



def test_collector_can_capture_initial_market_quotes_up_to_twelve_hours_pre_off():
    # Broader look-ahead lets the ledger learn price movement, but quote
    # timestamps and the strict race-off cutoff still guard every snapshot.
    assert MAX_LOOKAHEAD_MINUTES == 720
