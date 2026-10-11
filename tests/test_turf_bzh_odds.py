from src.model.turf_bzh_odds import build_snapshot


def payload(updated_at="2026-10-12T10:00:00+00:00"):
    return {
        "data": {
            "date": "2026-10-12",
            "code_course": "R1C1",
            "source": "pmu",
            "updated_at": updated_at,
            "partants": [
                {"num": 1, "cote": 4.5, "np": False},
                {"num": 2, "cote": 5.0, "np": False},
            ],
        },
        "meta": {"generated_at": updated_at, "temps_reel": True},
    }


def test_turf_bzh_adapter_maps_only_pre_race_prices_with_matching_roster():
    row = build_snapshot(
        payload(),
        race_key="2026-10-12|AUTEUIL|1",
        race_off_at="2026-10-12T10:15:00+00:00",
        source_url="https://www.turf.bzh/api/v1/courses/2026-10-12/R1C1/cotes",
        expected_course_code="R1C1",
        expected_runner_numbers={1, 2},
        captured_at="2026-10-12T10:01:00+00:00",
    )
    assert row["source_type"] == "tote_win"
    assert row["odds"] == {"1": 4.5, "2": 5.0}


def test_turf_bzh_adapter_rejects_post_off_prices_and_roster_mismatch():
    common = {
        "race_key": "2026-10-12|AUTEUIL|1",
        "race_off_at": "2026-10-12T10:15:00+00:00",
        "source_url": "https://www.turf.bzh/api/v1/courses/2026-10-12/R1C1/cotes",
        "expected_course_code": "R1C1",
        "expected_runner_numbers": {1, 2},
        "captured_at": "2026-10-12T10:16:00+00:00",
    }
    assert build_snapshot(payload(), **common) is None
    assert build_snapshot(
        payload(),
        **{**common, "captured_at": "2026-10-12T10:01:00+00:00", "expected_runner_numbers": {1, 2, 3}},
    ) is None
