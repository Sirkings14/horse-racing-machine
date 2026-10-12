from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.model.train_model as train_model


class TrainModelLabelPreflightTests(unittest.TestCase):
    def test_skips_candidate_before_creating_files_when_target_has_one_class(self):
        rows = [
            {"race_key": "R1", "top3": 1, "top4": 1, "top5": 1},
            {"race_key": "R1", "top3": 0, "top4": 1, "top5": 0},
            {"race_key": "R2", "top3": 1, "top4": 1, "top5": 1},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset_file = root / "training_dataset_clean.json"
            challenger_root = root / "challengers"
            dataset_file.write_text(json.dumps(rows), encoding="utf-8")

            with (
                patch.object(train_model, "DATASET_FILE", dataset_file),
                patch.object(train_model, "CHALLENGER_DIR", challenger_root),
                patch.object(train_model, "new_candidate_version") as new_version,
            ):
                result = train_model.main()

            self.assertIsNone(result)
            self.assertFalse(challenger_root.exists())
            new_version.assert_not_called()

    def test_all_targets_with_both_classes_pass_preflight(self):
        rows = [
            {"top3": 1, "top4": 1, "top5": 1},
            {"top3": 0, "top4": 0, "top5": 0},
        ]

        self.assertIsNone(train_model._insufficient_training_target_reason(rows))

    def test_target_without_known_labels_is_rejected(self):
        rows = [
            {"top3": 1, "top4": None, "top5": 0},
            {"top3": 0, "top4": "", "top5": 1},
        ]

        reason = train_model._insufficient_training_target_reason(rows)
        self.assertIn("top4 has no known binary labels", reason)


if __name__ == "__main__":
    unittest.main()
