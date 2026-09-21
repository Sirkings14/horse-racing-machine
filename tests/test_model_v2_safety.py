from __future__ import annotations

import unittest

from src.model.feature_drift import compare_feature_distributions
from src.model.logistic_model import LogisticModel


class ModelV2SafetyTests(unittest.TestCase):
    def test_cost_sensitive_probability_prior_correction(self):
        model = LogisticModel(
            feature_names=[],
            mean=[0.0] * 9,
            std=[1.0] * 9,
            intercept=0.0,
            coefficients=[0.0] * 9,
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
