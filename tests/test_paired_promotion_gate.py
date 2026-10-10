import unittest

from src.model.v3_train import _promotion_decision


class PairedPromotionGateTests(unittest.TestCase):
    def baseline_metrics(self):
        return {
            "winner_hit_rate_at_3": 0.48,
            "coverage3_lift_vs_random": 0.25,
            "brier": 0.15,
            "brier_baseline": 0.20,
            "ece": 0.05,
            "time_stability": [
                {"top3_coverage": 1.2},
                {"top3_coverage": 1.2},
                {"top3_coverage": 1.2},
            ],
            "average_actual_top3_covered_by_predicted_top3": 1.2,
        }

    def test_promotion_requires_material_paired_uplift_and_no_regression(self):
        paired = {"non_regression_pass": True, "material_uplift_pass": True}
        approved, reasons = _promotion_decision(
            self.baseline_metrics(), 500,
            calibration_gate={"brier": 0.1, "brier_baseline": 0.2, "ece": 0.05},
            paired_comparison=paired,
        )
        self.assertTrue(approved, reasons)

    def test_missing_paired_comparison_blocks_promotion(self):
        approved, reasons = _promotion_decision(
            self.baseline_metrics(), 500,
            calibration_gate={"brier": 0.1, "brier_baseline": 0.2, "ece": 0.05},
        )
        self.assertFalse(approved)
        self.assertIn("incumbent_reference_non_regression_failed", reasons)
        self.assertIn("no_material_uplift_over_legacy_feature_reference", reasons)

    def test_pairwise_regression_blocks_promotion(self):
        paired = {"non_regression_pass": False, "material_uplift_pass": True}
        approved, reasons = _promotion_decision(
            self.baseline_metrics(), 500,
            calibration_gate={"brier": 0.1, "brier_baseline": 0.2, "ece": 0.05},
            paired_comparison=paired,
        )
        self.assertFalse(approved)
        self.assertIn("incumbent_reference_non_regression_failed", reasons)


if __name__ == "__main__":
    unittest.main()
