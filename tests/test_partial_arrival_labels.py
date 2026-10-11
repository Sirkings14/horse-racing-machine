from src.dataset.build_dataset import extract_race_rows
from src.model.v3_model import fit_v3_model, known_binary_targets, evaluation_labels_complete


def _matched_record(arrival):
    horses = [
        {"number": number, "horse": f"HORSE {number}", "description": "",
         "weight": 60 + number, "draw": number}
        for number in range(1, 7)
    ]
    return {
        "match": {"status": "MATCHED"},
        "program": {
            "date": "2026-06-01",
            "source_file": "program.json",
            "race": {
                "track": "CAEN", "race_number": 1, "race_name": "TEST",
                "race_type": "PLAT", "distance": 1600, "runners_count": 6,
            },
            "horses": horses,
        },
        "result": {
            "date": "2026-06-01", "track": "CAEN", "race_number": 1,
            "source_file": "result.json", "arrival": arrival,
        },
    }


def test_three_place_arrival_does_not_create_false_top4_or_top5_negatives():
    rows = extract_race_rows(_matched_record([1, 2, 3]))
    assert len(rows) == 6
    by_number = {row["horse_number"]: row for row in rows}
    assert [by_number[number]["top3"] for number in range(1, 7)] == [1, 1, 1, 0, 0, 0]
    assert all(row["top4"] is None for row in rows)
    assert all(row["top5"] is None for row in rows)
    assert all(row["target_top4_known"] is False for row in rows)
    assert all(row["target_top5_known"] is False for row in rows)
    assert all(row["arrival_positions_available"] == 3 for row in rows)


def test_four_place_arrival_has_known_top4_but_not_top5_labels():
    rows = extract_race_rows(_matched_record([4, 2, 1, 5]))
    by_number = {row["horse_number"]: row for row in rows}
    assert [by_number[number]["top4"] for number in range(1, 7)] == [1, 1, 0, 1, 1, 0]
    assert all(row["top5"] is None for row in rows)
    assert all(row["target_top4_known"] is True for row in rows)
    assert all(row["target_top5_known"] is False for row in rows)


def test_full_five_place_arrival_creates_complete_top5_labels():
    rows = extract_race_rows(_matched_record([4, 2, 1, 5, 3]))
    by_number = {row["horse_number"]: row for row in rows}
    assert [by_number[number]["top5"] for number in range(1, 7)] == [1, 1, 1, 1, 1, 0]
    assert all(row["target_top5_known"] is True for row in rows)


def test_duplicate_or_out_of_roster_arrival_is_rejected():
    assert extract_race_rows(_matched_record([1, 2, 2, 4, 5])) == []
    assert extract_race_rows(_matched_record([1, 2, 3, 7, 5])) == []


def test_unknown_binary_targets_are_masked():
    rows = [
        {"top5": 1}, {"top5": 0}, {"top5": None},
        {"top5": ""}, {"top5": float("nan")}, {"top5": 2},
    ]
    indices, labels = known_binary_targets(rows, "top5")
    assert indices == [0, 1]
    assert labels == [1, 0]


def test_model_training_excludes_unknown_targets_instead_of_counting_them_as_losses():
    rows = []
    for number, target in enumerate([1, 0, None, None], start=1):
        rows.append({
            "race_key": "2026-06-01|CAEN|1",
            "horse_number": number,
            "horse_name": f"HORSE {number}",
            "distance": 1600,
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
    model = fit_v3_model(rows, target_field="top5", epochs=3, learning_rate=0.01, l2=0.0)
    assert model.positive_weight == 1.0


def test_model_training_fails_closed_if_no_labels_are_known():
    rows = [{"horse_name": "A", "top5": None}, {"horse_name": "B", "top5": None}]
    try:
        fit_v3_model(rows, target_field="top5", epochs=1)
    except ValueError as error:
        assert "No known binary labels" in str(error)
    else:
        raise AssertionError("Expected unknown-label-only training to fail closed")



def test_backtest_rejects_incomplete_winner_or_top3_label_sets():
    complete = [
        {"won": 1, "top3": 1},
        {"won": 0, "top3": 1},
        {"won": 0, "top3": 0},
    ]
    incomplete = [
        {"won": 1, "top3": 1},
        {"won": 0, "top3": 1},
        {"won": 0, "top3": None},
    ]
    missing_winner = [
        {"won": 1, "top3": 1},
        {"won": None, "top3": 0},
    ]
    assert evaluation_labels_complete(complete) is True
    assert evaluation_labels_complete(incomplete) is False
    assert evaluation_labels_complete(missing_winner) is False
