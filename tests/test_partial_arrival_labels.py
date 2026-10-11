from src.dataset.build_dataset import extract_race_rows
from src.model.v3_model import fit_v3_model, known_binary_targets, evaluation_labels_complete


def _matched_record(arrival):
    horses = [
        {"number": number, "horse": f"HORSE {number}", "description": "", "weight": 60 + number, "draw": number}
        for number in range(1, 7)
    ]
    return {
        "match": {"status": "MATCHED"},
        "program": {
            "date": "2026-06-01", "source_file": "program.json",
            "race": {"track": "CAEN", "race_number": 1, "race_name": "TEST", "race_type": "PLAT", "distance": 1600, "runners_count": 6},
            "horses": horses,
        },
        "result": {"date": "2026-06-01", "track": "CAEN", "race_number": 1, "source_file": "result.json", "arrival": arrival},
    }


def test_partial_three_place_arrival_masks_top4_top5_negatives():
    rows = extract_race_rows(_matched_record([1, 2, 3]))
    assert len(rows) == 6
    assert [r["top3"] for r in rows[:3]] == [1, 1, 1]
    assert all(r["top4"] is None and r["top5"] is None for r in rows)
    assert all(not r["target_top4_known"] and not r["target_top5_known"] for r in rows)


def test_two_place_arrival_keeps_observed_top3_positives_but_masks_unknown_negatives():
    rows = extract_race_rows(_matched_record([2, 1]))
    by_number = {r["horse_number"]: r for r in rows}
    assert by_number[1]["top3"] == 1
    assert by_number[2]["top3"] == 1
    assert all(by_number[n]["top3"] is None for n in (3, 4, 5, 6))
    assert by_number[1]["top4"] == 1
    assert by_number[2]["top5"] == 1


def test_four_place_arrival_only_defines_top4_not_top5():
    rows = extract_race_rows(_matched_record([4, 2, 1, 5]))
    by_number = {r["horse_number"]: r for r in rows}
    assert [by_number[n]["top4"] for n in range(1, 7)] == [1, 1, 0, 1, 1, 0]
    assert all(r["top5"] is None for r in rows)


def test_full_five_place_arrival_defines_top5():
    rows = extract_race_rows(_matched_record([4, 2, 1, 5, 3]))
    by_number = {r["horse_number"]: r for r in rows}
    assert [by_number[n]["top5"] for n in range(1, 7)] == [1, 1, 1, 1, 1, 0]


def test_ambiguous_arrivals_are_rejected():
    assert extract_race_rows(_matched_record([1, 2, 2, 4, 5])) == []
    assert extract_race_rows(_matched_record([1, 2, 3, 7, 5])) == []


def test_unknown_targets_are_masked_not_counted_as_losses():
    rows = [{"top5": 1}, {"top5": 0}, {"top5": None}, {"top5": ""}, {"top5": float("nan")}, {"top5": 2}]
    indices, labels = known_binary_targets(rows, "top5")
    assert indices == [0, 1]
    assert labels == [1, 0]


def test_training_fails_closed_when_no_labels_are_known():
    try:
        fit_v3_model([{"horse_name": "A", "top5": None}, {"horse_name": "B", "top5": None}], target_field="top5", epochs=1)
    except ValueError as error:
        assert "No known binary labels" in str(error)
    else:
        raise AssertionError("Expected training with unknown labels to fail")


def test_backtest_requires_complete_labels_for_evaluation():
    assert evaluation_labels_complete([{"won": 1, "top3": 1}, {"won": 0, "top3": 0}])
    assert not evaluation_labels_complete([{"won": 1, "top3": 1}, {"won": 0, "top3": None}])
