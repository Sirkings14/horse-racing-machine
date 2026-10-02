import unittest

from src.learning.result_truth import validate_arrival


class ResultTruthTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "2026-09-22|AUTEUIL|4": {
                "horse_numbers": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
                "runners_count": 16,
                "source_file": "program.json",
            }
        }

    def test_rejects_non_runner_numbers(self):
        result = validate_arrival(
            "2026-09-22|AUTEUIL|4",
            [1, 4, 3, 700, 64, 5],
            self.index,
        )
        self.assertFalse(result["accepted_for_learning"])
        self.assertIn("arrival_contains_non_runner_numbers", result["reason"])

    def test_accepts_valid_top_three(self):
        result = validate_arrival(
            "2026-09-22|AUTEUIL|4",
            [1, 4, 3, 5, 6],
            self.index,
        )
        self.assertTrue(result["accepted_for_learning"])

    def test_rejects_duplicate_positions(self):
        result = validate_arrival(
            "2026-09-22|AUTEUIL|4",
            [1, 4, 4],
            self.index,
        )
        self.assertFalse(result["accepted_for_learning"])
        self.assertIn("duplicate_arrival_numbers", result["reason"])


if __name__ == "__main__":
    unittest.main()
