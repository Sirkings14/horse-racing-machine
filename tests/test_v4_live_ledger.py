import unittest

from src.learning.evaluate_predictions import V4_MODES, _build_v4_performance, evaluate


class TestV4LiveLedger(unittest.TestCase):
    def test_v4_no_bet_preserves_model_candidates_for_evaluation(self):
        prediction = {
            "race_key": "2026-10-06|AUTEUIL|1",
            "prediction_id": "test",
            "generated_at": "2026-10-06T12:00:00+00:00",
            "model_version": "v4-evidence-no-press",
            "mode": "v3_evidence_no_press",
            "recommended_numbers": [],
            "final_five": [],
            "live_decision": "NO_BET",
            "confidence": "low",
            "model_agreement": "low",
            "autopilot_guard": {
                "decision": "PASS",
                "gate_reasons": [
                    "insufficient_verified_history",
                    "low_model_confidence",
                    "economic_validation_unavailable",
                ],
            },
            "ranked_horses": [
                {"horse_number": 3},
                {"horse_number": 4},
                {"horse_number": 1},
                {"horse_number": 2},
                {"horse_number": 5},
            ],
        }
        result = {
            "arrival": [4, 7, 3, 9, 1],
            "winner": 4,
            "truth_validation": {"accepted_for_learning": True},
        }

        evaluation = evaluate(prediction, result)

        self.assertEqual(evaluation["prediction"]["model_candidates"], [3, 4, 1, 2, 5])
        self.assertEqual(evaluation["prediction"]["recommended_numbers"], [])
        self.assertEqual(evaluation["metrics"]["model_candidate_hit_count"], 3)
        self.assertTrue(evaluation["metrics"]["winner_in_top3"])
        self.assertEqual(evaluation["prediction"]["live_decision"], "NO_BET")

    def test_v4_report_never_calls_no_bet_a_bet(self):
        rows = [{
            "mode": "v3_evidence_no_press",
            "status": "result_verified",
            "prediction": {
                "live_decision": "NO_BET",
                "confidence": "low",
                "model_agreement": "low",
            },
            "metrics": {
                "winner_hit": 0,
                "winner_in_top3": 1,
                "winner_in_top5": 1,
                "actual_top3_covered_by_predicted_top3": 1,
                "actual_top3_covered_by_predicted_top5": 2,
                "model_candidate_hit_count": 2,
            },
        }]
        report = _build_v4_performance(rows)
        self.assertEqual(report["verified_races"], 1)
        self.assertEqual(report["no_bet_races"], 1)
        self.assertEqual(report["betting_clear_races"], 0)
        self.assertTrue(report["policy"]["predictive_validation_is_not_profitability_validation"])

    def test_supported_modes_are_explicit(self):
        self.assertEqual(V4_MODES, {"v3_evidence_no_press", "v4_evidence_no_press"})


if __name__ == "__main__":
    unittest.main()
