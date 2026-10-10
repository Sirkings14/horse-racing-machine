from src.model.race_type import (
    canonical_race_type,
    race_type_family,
    race_type_feature_groups,
)
from src.model.v3_features import FEATURE_NAMES, build_v3_matrix


def test_french_accents_and_aliases_are_normalized():
    assert canonical_race_type("MONTÉ") == "MONTE"
    assert canonical_race_type("trot monté") == "MONTE"
    assert canonical_race_type("ATTELÉ") == "ATTELE"
    assert canonical_race_type("flat racing") == "PLAT"
    assert canonical_race_type("steeple chase") == "STEEPLE-CHASE"
    assert canonical_race_type("hurdles") == "HAIES"


def test_unknown_race_type_is_preserved_and_not_misclassified():
    assert canonical_race_type("unknown experimental discipline") == "UNKNOWN EXPERIMENTAL DISCIPLINE"
    assert race_type_family("unknown experimental discipline") == "unknown"
    assert race_type_feature_groups("unknown experimental discipline") == (0.0, 0.0, 0.0)


def test_harness_and_mounted_trot_are_distinguished_but_v3_flags_stay_compatible():
    assert race_type_family("ATTELE") == "trot_harness"
    assert race_type_family("MONTÉ") == "trot_mounted"
    assert race_type_feature_groups("ATTELE") == (0.0, 1.0, 0.0)
    assert race_type_feature_groups("MONTÉ") == (0.0, 1.0, 0.0)


def test_v3_feature_flags_handle_accented_trot_labels():
    rows = [
        {"horse_name": "A", "race_type": "MONTÉ", "distance": 2700, "runners_count": 12},
        {"horse_name": "B", "race_type": "PLAT", "distance": 2000, "runners_count": 12},
        {"horse_name": "C", "race_type": "HAIES", "distance": 3500, "runners_count": 12},
    ]
    matrix = build_v3_matrix(rows)
    flat_idx = FEATURE_NAMES.index("race_type_flat")
    trot_idx = FEATURE_NAMES.index("race_type_trot")
    obstacle_idx = FEATURE_NAMES.index("race_type_jump")
    assert matrix[0, trot_idx] == 1.0
    assert matrix[1, flat_idx] == 1.0
    assert matrix[2, obstacle_idx] == 1.0
