from __future__ import annotations

import unittest

from src.model.feature_drift import compare_feature_distributions
from src.model.logistic_model import LogisticModel
from src.model.feature_engineering import FEATURE_NAMES


class ModelV2SafetyTests(unittest.TestCase):
    def test_cost_sensitive_probability_prior_correction(self):
        model = LogisticModel(
            feature_names=[],
            mean=[0.0] * len(FEATURE_NAMES),
            std=[1.0] * len(FEATURE_NAMES),
            intercept=0.0,
            coefficients=[0.0] * len(FEATURE_NAMES),
            positive_weight=2.0,
        )
        self.assertAlmostEqual(float(model.predict_weighted_proba([{}])[0]), 0.5)
        self.assertAlmostEqual(float(model.predict_proba([{}])[0]), 1.0 / 3.0)

    def test_single_race_drift_is_not_classified_as_severe(self):
        reference = [{"favorites_rank": 1, "form_rank": 1} for _ in range(100)]
        current = [{"favorites_rank": 10, "form_rank": 10} for _ in range(13)]
        report = compare_feature_distributions(reference, current, "test")
        self.assertEqual(report["status"], "insufficient_current_sample")
        self.assertEqual(report["overall_severity"], "unrated")
        self.assertEqual(report["severe_feature_count"], 0)


if __name__ == "__main__":
    unittest.main()


class TestOrderProbabilitySemantics(unittest.TestCase):
    def test_order_output_does_not_claim_calibrated_win_probability(self):
        from src.model.order_model import OrderModel
        model = OrderModel(
            feature_names=list(FEATURE_NAMES), mean=[0.0] * len(FEATURE_NAMES), std=[1.0] * len(FEATURE_NAMES), coefficients=[1.0] * len(FEATURE_NAMES)
        )
        result = model.predict_order([
            {"horse_number": 1, "x": 1.0},
            {"horse_number": 2, "x": 0.0},
        ])
        self.assertIn("order_selection_weight", result[0])
        self.assertNotIn("order_win_probability", result[0])
