import json
from pathlib import Path

from src.dataset.recent_verified_supplement import (
    collect_recent_verified_rows,
    rows_from_verified_race,
    strict_arrival,
)
from src.learning.result_truth import canonical_key
from src.model.v3_model import fit_v3_model, known_binary_targets


def _program():
    horses = []
    for number in range(1, 7):
        horses.append({
            "number": number,
            "horse": f"HORSE {number}",
            "performance": "1.2.3.4.5",
            "gains": number * 10000,
            "sex": "H",
            "age": 5,
            "weight": 62 + number / 10,
            "draw": number,
            "listed_chrono": "1.12.3",
            "listed_distance": "2700.M",
            "trainer": "TRAINER A",
            "jockey": "JOCKEY A",
            "driver": "DRIVER A",
            "owner": "OWNER A",
        })
    return {
        "document_type": "program",
        "date": "2026-06-01",
        "race": {
            "track": "CAEN",
            "race_number": 1,
            "race_name": "TEST RACE",
            "race_type": "ATTELE",
            "distance": 2700,
            "runners_count": 6,
            "prize_euros": 25000,
        },
        "horses": horses,
        # Explicitly conflicting post-race metadata must be ignored.
        "published_arrival": [6, 5, 4],
        "press_odds": {"paris_turf": {"1": {"decimal": 1.05}}},
    }


def _program_index():
    return {
        canonical_key("2026-06-01", "CAEN", 1): {
            "horse_numbers": set(range(1, 7)),
            "runners_count": 6,
            "source_file": "test_roster",
            "conflict": False,
        }
    }


def _write_program(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "program.json").write_text(json.dumps(_program()), encoding="utf-8")


def _write_result(directory: Path, file_name: str, arrival: list[int], source_file: str | None = None):
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_type": "result",
        "date": "2026-06-01",
        "track": "CAEN",
        "races": [{"race_number": 1, "arrival": arrival}],
    }
    if source_file:
        payload["source_file"] = source_file
    (directory / file_name).write_text(json.dumps(payload), encoding="utf-8")


def _write_raw_result(directory: Path, file_name: str, arrival_line: str):
    directory.mkdir(parents=True, exist_ok=True)
    text = (
        "DU : 01 - 06 - 2026 - REUNION - 1 - ( CAEN )\n"
        f"{arrival_line}\n"
    )
    (directory / file_name).write_text(text, encoding="utf-8")


def test_strict_arrival_rejects_ambiguous_shapes_and_invalid_numbers():
    assert strict_arrival("[1, 2, 3, 4]") == [1, 2, 3, 4]
    assert strict_arrival([1, 2.0, "3"]) == [1, 2, 3]
    assert strict_arrival([[1, 2], [3]]) is None
    assert strict_arrival([1, 2.5, 3]) is None
    assert strict_arrival([1, True, 3]) is None
    assert strict_arrival("not a result") is None


def test_partial_arrival_keeps_top3_truth_but_masks_all_top5_labels():
    program = _program()
    truth = {
        "accepted_for_learning": True,
        "reason": "validated_against_program_roster",
        "race_key": canonical_key("2026-06-01", "CAEN", 1),
        "arrival_positions_available": 4,
    }
    rows = rows_from_verified_race(
        program,
        truth["race_key"],
        [1, 2, 3, 4],
        truth,
        "program.json",
        "result.json",
    )
    assert len(rows) == 6
    by_number = {row["horse_number"]: row for row in rows}
    assert [by_number[n]["top3"] for n in range(1, 7)] == [1, 1, 1, 0, 0, 0]
    assert by_number[4]["finish_position"] == 4
    assert all(row["top5"] is None for row in rows)
    assert all(row["target_label_status"]["top5_known"] is False for row in rows)
    # Published arrival and press odds never override official result labels.
    assert by_number[6]["top3"] == 0
    assert "press_odds" not in by_number[1]
    assert "published_arrival" not in by_number[1]


def test_recent_verified_supplement_joins_program_and_official_result(tmp_path):
    programs = tmp_path / "programs"
    results = tmp_path / "results"
    audit_path = tmp_path / "audit" / "recent.json"
    _write_program(programs)
    _write_result(results, "result.json", [1, 2, 3, 4, 5])
    base_rows = [{"date": "2026-05-05", "track": "VINCENNES", "race_number": 1}]
    rows, audit = collect_recent_verified_rows(
        base_rows,
        after_date="2026-05-05",
        program_index=_program_index(),
        program_dir=programs,
        result_dir=results,
        audit_path=audit_path,
        as_of_date="2026-06-02",
    )
    assert len(rows) == 6
    assert audit["supplemented_races"] == 1
    assert audit["top5_label_complete_races"] == 1
    assert {row["top5"] for row in rows} == {0, 1}
    assert all(row["result_truth_verified"] is True for row in rows)
    assert audit_path.exists()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["supplemented_runner_rows"] == 6


def test_conflicting_official_arrivals_quarantine_the_whole_race(tmp_path):
    programs = tmp_path / "programs"
    results = tmp_path / "results"
    _write_program(programs)
    _write_result(results, "result_a.json", [1, 2, 3, 4, 5])
    _write_result(results, "result_b.json", [2, 1, 3, 4, 5])
    rows, audit = collect_recent_verified_rows(
        [{"date": "2026-05-05", "track": "VINCENNES", "race_number": 1}],
        after_date="2026-05-05",
        program_index=_program_index(),
        program_dir=programs,
        result_dir=results,
        audit_path=None,
        as_of_date="2026-06-02",
    )
    assert rows == []
    assert audit["conflicting_result_races"] == 1
    assert audit["supplemented_races"] == 0


def test_recent_supplement_reparses_raw_txt_and_does_not_invent_fourth_place(tmp_path):
    programs = tmp_path / "programs"
    results = tmp_path / "results"
    raw_results = tmp_path / "processed_results"
    _write_program(programs)
    _write_result(results, "result.json", [1, 2, 3, 5], source_file="result.txt")
    _write_raw_result(
        raw_results,
        "result.txt",
        "1ère 1 - 2 - 3 6 1 000 33 1 - 2 4 500 90",
    )
    rows, audit = collect_recent_verified_rows(
        [{"date": "2026-05-05", "track": "VINCENNES", "race_number": 1}],
        after_date="2026-05-05",
        program_index=_program_index(),
        program_dir=programs,
        result_dir=results,
        audit_path=None,
        as_of_date="2026-06-02",
        raw_result_dir=raw_results,
    )
    assert len(rows) == 6
    assert audit["raw_result_documents_reparsed"] == 1
    assert audit["supplemented_races"] == 1
    assert audit["top5_label_complete_races"] == 0
    assert audit["top5_label_incomplete_races"] == 1
    assert {row["top3"] for row in rows} == {0, 1}
    assert all(row["top4"] is None for row in rows)
    assert all(row["top5"] is None for row in rows)
    assert {row["finish_position"] for row in rows if row["finish_position"] is not None} == {1, 2, 3}


def test_recent_supplement_skips_races_already_in_base_dataset(tmp_path):
    programs = tmp_path / "programs"
    results = tmp_path / "results"
    _write_program(programs)
    _write_result(results, "result.json", [1, 2, 3, 4, 5])
    base_rows = [{
        "date": "2026-06-01",
        "track": "CAEN",
        "race_number": 1,
    }]
    rows, audit = collect_recent_verified_rows(
        base_rows,
        after_date="2026-05-05",
        program_index=_program_index(),
        program_dir=programs,
        result_dir=results,
        audit_path=None,
        as_of_date="2026-06-02",
    )
    assert rows == []
    assert audit["supplemented_races"] == 0


def test_unknown_labels_are_masked_not_converted_to_losses_during_training():
    rows = []
    targets = [1, 0, None, None]
    for number, target in enumerate(targets, start=1):
        rows.append({
            "race_key": "2026-06-01|CAEN|1",
            "horse_number": number,
            "horse_name": f"HORSE {number}",
            "distance": 2700,
            "runners_count": 4,
            "history_starts": number,
            "history_win_rate": number / 10,
            "history_top3_rate": number / 5,
            "history_top5_rate": number / 4,
            "history_recent_top3_rate": number / 5,
            "history_recent_top5_rate": number / 4,
            "history_recent_avg_finish": number,
            "course_top3_rate": number / 5,
            "distance_top3_rate": number / 5,
            "won": int(number == 1),
            "top3": int(number <= 3),
            "top5": target,
        })
    indices, labels = known_binary_targets(rows, "top5")
    assert indices == [0, 1]
    assert labels == [1, 0]
    model = fit_v3_model(rows, target_field="top5", epochs=3, learning_rate=0.01, l2=0.0)
    assert model.positive_weight == 1.0
