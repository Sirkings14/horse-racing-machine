from pathlib import Path
import json

from src.dataset.pmu_arrival_source import (
    load_local_evidence,
    pmu_participants_url,
    probe,
    strict_arrival,
    strict_positive_int,
    validate_pmu_payload,
)


def test_endpoint_url_is_specific_to_date_meeting_and_race():
    assert pmu_participants_url("2026-10-10", 1, 4).endswith("/10102026/R1/C4/participants")


def test_strict_positive_integer_never_rounds_fractions_or_accepts_bool():
    assert strict_positive_int(5) == 5
    assert strict_positive_int("05") == 5
    assert strict_positive_int(5.0) == 5
    assert strict_positive_int(True) is None
    assert strict_positive_int(5.5) is None
    assert strict_positive_int("5.0") is None
    assert strict_positive_int(0) is None


def test_strict_arrival_rejects_duplicates_and_nested_shapes():
    assert strict_arrival([9, 10, "4", 1]) == [9, 10, 4, 1]
    assert strict_arrival([1, 2, 2]) is None
    assert strict_arrival([[1, 2], [3]]) is None
    assert strict_arrival([1, True, 3]) is None


def _payload(order=(9, 10, 4, 1, 5)):
    return {
        "participants": [
            {"numPmu": horse, "ordreArrivee": rank, "nomCheval": f"HORSE {horse}", "cotes": [99.0]}
            for rank, horse in enumerate(order, start=1)
        ]
    }


def test_valid_top5_must_match_roster_and_local_four_place_prefix():
    result = validate_pmu_payload(
        _payload(),
        {1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
        [9, 10, 4, 1],
    )
    assert result["accepted"] is True
    assert result["top5_numbers"] == [9, 10, 4, 1, 5]
    assert result["top5_details"][3] == {"rank": 4, "horse_number": 1, "horse_name": "HORSE 1"}
    assert result["matched_local_prefix_positions"] == 4
    assert result["policy"]["odds_and_market_fields_ignored"] is True


def test_missing_fifth_position_is_rejected():
    result = validate_pmu_payload(_payload(order=(9, 10, 4, 1)), {1, 4, 9, 10}, [9, 10, 4, 1])
    assert result["accepted"] is False
    assert result["reason"] == "five_unique_arrival_positions_unavailable"


def test_duplicate_arrival_rank_is_rejected():
    payload = _payload()
    payload["participants"].append({"numPmu": 6, "ordreArrivee": 5})
    result = validate_pmu_payload(payload, {1, 4, 5, 6, 9, 10}, [9, 10, 4, 1])
    assert result["accepted"] is False
    assert result["reason"] == "duplicate_or_tied_arrival_position"


def test_runner_outside_roster_is_rejected():
    result = validate_pmu_payload(_payload(), {1, 2, 3, 4, 9}, [9, 10, 4, 1])
    assert result["accepted"] is False
    assert result["reason"] == "top5_contains_runner_outside_declared_roster"


def test_local_prefix_mismatch_is_rejected():
    result = validate_pmu_payload(_payload(), {1, 2, 3, 4, 5, 9, 10}, [9, 10, 5, 1])
    assert result["accepted"] is False
    assert result["reason"] == "pmu_top5_disagrees_with_local_result_prefix"


def test_local_evidence_requires_exact_roster_and_local_result_prefix(tmp_path: Path):
    programs = tmp_path / "programs"
    results = tmp_path / "results"
    programs.mkdir()
    results.mkdir()
    program = {
        "document_type": "program",
        "date": "2026-10-10",
        "race": {"track": "CAEN", "race_number": 4, "race_type": "ATTELE", "runners_count": 5},
        "horses": [{"number": number, "horse": f"H{number}", "performance": "1.2.3"} for number in range(1, 6)],
        "published_arrival": [1, 2, 3, 4, 5],
        "press_odds": {"ignore": True},
    }
    result = {
        "document_type": "result",
        "date": "2026-10-10",
        "track": "CAEN",
        "meeting": 1,
        "races": [{"race_number": 4, "arrival": [4, 2, 1, 5]}],
    }
    (programs / "program.json").write_text(json.dumps(program), encoding="utf-8")
    (results / "result.json").write_text(json.dumps(result), encoding="utf-8")
    local = load_local_evidence("2026-10-10", "CAEN", 1, 4, programs, results)
    assert local["accepted"] is True
    assert local["roster_numbers"] == [1, 2, 3, 4, 5]
    assert local["local_result_prefix"] == [4, 2, 1, 5]
    assert local["local_result_prefix"] != program["published_arrival"]


def test_probe_records_source_unavailable_without_training_side_effects(tmp_path: Path, monkeypatch):
    import requests
    import src.dataset.pmu_arrival_source as module

    programs = tmp_path / "programs"
    results = tmp_path / "results"
    programs.mkdir()
    results.mkdir()
    program = {
        "document_type": "program", "date": "2026-10-10",
        "race": {"track": "CAEN", "race_number": 4, "race_type": "ATTELE", "runners_count": 5},
        "horses": [{"number": number, "horse": f"H{number}"} for number in range(1, 6)],
    }
    result = {"document_type": "result", "date": "2026-10-10", "track": "CAEN", "meeting": 1,
              "races": [{"race_number": 4, "arrival": [4, 2, 1, 5]}]}
    (programs / "program.json").write_text(json.dumps(program), encoding="utf-8")
    (results / "result.json").write_text(json.dumps(result), encoding="utf-8")

    def unavailable(*args, **kwargs):
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr(module.requests, "get", unavailable)
    report_path = tmp_path / "audit.json"
    report = probe("2026-10-10", "CAEN", 1, 4, programs, results, report_path)
    assert report["status"] == "source_unavailable"
    assert report["reason"] == "Timeout"
    assert report["policy"]["writes_training_dataset"] is False
    assert report["policy"]["changes_betting_guard"] is False
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "source_unavailable"
