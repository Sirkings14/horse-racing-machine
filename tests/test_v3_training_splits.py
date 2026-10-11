import pytest

from src.model.v3_features import tail_complete_races
from src.model.v3_train import chronological_group_split


def _race(key, date_text, runners=3):
    return [
        {
            "race_key": key,
            "date": date_text,
            "horse_number": number,
            "top3": int(number <= 3),
        }
        for number in range(1, runners + 1)
    ]


def test_row_budget_keeps_newest_races_whole_even_if_budget_is_exceeded():
    rows = (
        _race("2026-01-01|A|1", "2026-01-01", 3)
        + _race("2026-01-02|A|1", "2026-01-02", 4)
        + _race("2026-01-03|A|1", "2026-01-03", 2)
    )
    kept = tail_complete_races(rows, max_rows=5)
    counts = {}
    for row in kept:
        counts[row["race_key"]] = counts.get(row["race_key"], 0) + 1

    assert counts == {
        "2026-01-02|A|1": 4,
        "2026-01-03|A|1": 2,
    }
    assert len(kept) == 6  # whole-race preservation beats an exact row cap


def test_chronological_split_keeps_all_same_day_races_on_one_side():
    groups = {}
    for day in range(1, 9):
        date_text = f"2026-01-{day:02d}"
        for race_number in (1, 2):
            key = f"{date_text}|TRACK|{race_number}"
            groups[key] = _race(key, date_text, runners=4)

    train_keys, calibration_keys, date_by_key = chronological_group_split(
        groups, train_fraction=0.75
    )
    train_dates = {date_by_key[key] for key in train_keys}
    calibration_dates = {date_by_key[key] for key in calibration_keys}

    assert train_keys and calibration_keys
    assert train_dates.isdisjoint(calibration_dates)
    assert max(train_dates) < min(calibration_dates)
    assert len(train_dates | calibration_dates) == 8
    for date_text in train_dates | calibration_dates:
        same_day_keys = [key for key, value in date_by_key.items() if value == date_text]
        assert all(key in train_keys for key in same_day_keys) or all(
            key in calibration_keys for key in same_day_keys
        )


def test_chronological_split_fails_closed_when_calibration_cannot_be_separated():
    groups = {
        "2026-01-01|TRACK|1": _race("2026-01-01|TRACK|1", "2026-01-01"),
        "2026-01-02|TRACK|1": _race("2026-01-02|TRACK|1", "2026-01-02"),
    }
    with pytest.raises(ValueError, match="at least three distinct dates"):
        chronological_group_split(groups)


def test_chronological_split_rejects_race_group_with_conflicting_dates():
    groups = {
        "2026-01-01|TRACK|1": [
            {"race_key": "2026-01-01|TRACK|1", "date": "2026-01-01"},
            {"race_key": "2026-01-01|TRACK|1", "date": "2026-01-02"},
        ],
        "2026-01-03|TRACK|1": _race("2026-01-03|TRACK|1", "2026-01-03"),
        "2026-01-04|TRACK|1": _race("2026-01-04|TRACK|1", "2026-01-04"),
    }
    with pytest.raises(ValueError, match="multiple or missing dates"):
        chronological_group_split(groups)
