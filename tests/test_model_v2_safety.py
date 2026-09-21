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

    def test_pass_gate_blocks_disagreement(self):
        from src.model.autopilot_guard import build_autopilot_guard
        result = build_autopilot_guard({
            "monitoring": {"agreement": "meaningful_disagreement"},
            "ranked_horses": [
                {"horse_number": 1, "probability_top3": 0.21},
                {"horse_number": 2, "probability_top3": 0.20},
            ],
            "difficulty": {"bucket": "medium"},
        })
        self.assertEqual(result["decision"], "PASS")
        self.assertIn("engine_disagreement_or_unavailable", result["gate_reasons"])

    def test_play_candidate_requires_clean_evidence(self):
        from src.model.autopilot_guard import build_autopilot_guard
        result = build_autopilot_guard({
            "monitoring": {"agreement": "strong_agreement"},
            "ranked_horses": [
                {"horse_number": 1, "probability_top3": 0.30},
                {"horse_number": 2, "probability_top3": 0.20},
                {"horse_number": 3, "probability_top3": 0.15},
                {"horse_number": 4, "probability_top3": 0.10},
                {"horse_number": 5, "probability_top3": 0.05},
            ],
            "difficulty": {"bucket": "low"},
        })
        self.assertEqual(result["decision"], "PLAY_CANDIDATE")

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
            feature_names=["x"], mean=[0.0] * 9, std=[1.0] * 9, coefficients=[1.0] * 9
        )
        result = model.predict_order([
            {"horse_number": 1, "x": 1.0},
            {"horse_number": 2, "x": 0.0},
        ])
        self.assertIn("order_selection_weight", result[0])
        self.assertNotIn("order_win_probability", result[0])
