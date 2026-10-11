from __future__ import annotations

import unittest

import numpy as np

from src.model.logistic_model import fit_top3_model, known_binary_targets


class LogisticModelPartialTargetTests(unittest.TestCase):
    def setUp(self):
        self.known_rows = [
            {"horse_number": 1, "top3": 1, "favorites_rank": 1, "form_rank": 2, "distance": 1600, "runners_count": 10},
            {"horse_number": 2, "top3": 0, "favorites_rank": 4, "form_rank": 5, "distance": 1600, "runners_count": 10},
            {"horse_number": 3, "top3": 1, "favorites_rank": 2, "form_rank": 1, "distance": 2000, "runners_count": 12},
            {"horse_number": 4, "top3": 0, "favorites_rank": 7, "form_rank": 8, "distance": 2000, "runners_count": 12},
        ]

    def test_unknown_targets_are_masked_not_counted_as_negative(self):
        rows = self.known_rows + [
            {"horse_number": 5, "top3": None, "favorites_rank": 3, "distance": 1800, "runners_count": 11},
            {"horse_number": 6, "top3": "", "favorites_rank": 9, "distance": 1800, "runners_count": 11},
            {"horse_number": 7, "top3": float("nan"), "favorites_rank": 5, "distance": 1800, "runners_count": 11},
            {"horse_number": 8, "top3": 2, "favorites_rank": 6, "distance": 1800, "runners_count": 11},
        ]

        indices, labels = known_binary_targets(rows, "top3")
        self.assertEqual(indices, [0, 1, 2, 3])
        self.assertEqual(labels, [1, 0, 1, 0])

        baseline = fit_top3_model(self.known_rows, target_field="top3", epochs=8)
        with_unknowns = fit_top3_model(rows, target_field="top3", epochs=8)
        self.assertTrue(np.allclose(baseline.mean, with_unknowns.mean))
        self.assertTrue(np.allclose(baseline.std, with_unknowns.std))
        self.assertAlmostEqual(baseline.intercept, with_unknowns.intercept)
        self.assertTrue(np.allclose(baseline.coefficients, with_unknowns.coefficients))
        self.assertAlmostEqual(baseline.positive_weight, with_unknowns.positive_weight)

    def test_training_fails_closed_when_no_known_binary_labels_exist(self):
        rows = [{"horse_number": 1, "top5": None}, {"horse_number": 2, "top5": ""}]
        with self.assertRaisesRegex(ValueError, "No known binary labels available for target top5"):
            fit_top3_model(rows, target_field="top5", epochs=1)

    def test_known_labels_must_contain_positive_and_negative_examples(self):
        rows = [{"horse_number": 1, "top4": 1}, {"horse_number": 2, "top4": 1}, {"horse_number": 3, "top4": None}]
        with self.assertRaisesRegex(ValueError, "positive and negative examples"):
            fit_top3_model(rows, target_field="top4", epochs=1)


if __name__ == "__main__":
    unittest.main()
