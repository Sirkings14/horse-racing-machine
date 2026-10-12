import unittest

from src.model.live_market_comparison import build_comparison, build_settlement_metrics


def valid_snapshot(**overrides):
    snapshot = {
        "race_key": "2026-10-12|MARSEILLE-BORELY|4",
        "captured_at": "2026-10-12T02:07:28+00:00",
        "price_timestamp": "2026-10-12T02:07:28+00:00",
        "race_off_at": "2026-10-12T11:55:00+00:00",
        "source": "PMU public live JSON (undocumented)",
        "source_type": "tote_win",
        "market_type": "winner",
        "source_url": "https://example.com/race/4",
        "odds": {"1": 3.0, "2": 5.0, "3": 10.0, "4": 20.0, "5": 50.0},
    }
    snapshot.update(overrides)
    return snapshot


def valid_prediction(**overrides):
    prediction = {
        "race_key": "2026-10-12|MARSEILLE-BORELY|4",
        "generated_at": "2026-10-12T02:04:22+00:00",
        "model_version": "test-model",
        "model_fingerprint": "abc123",
        "race": {"runners_count": 5},
        "live_decision": "NO_BET",
        "confidence": "low",
        "model_agreement": "low",
        "recommended_numbers": [],
        "no_bet_reason": ["low_model_confidence"],
        "ranked_horses": [
            {"horse_number": 1, "horse_name": "HORSE ONE", "probability_winner": 0.40, "predicted_rank": 1},
            {"horse_number": 2, "horse_name": "HORSE TWO", "probability_winner": 0.25, "predicted_rank": 2},
            {"horse_number": 3, "horse_name": "HORSE THREE", "probability_winner": 0.18, "predicted_rank": 3},
            {"horse_number": 4, "horse_name": "HORSE FOUR", "probability_winner": 0.10, "predicted_rank": 4},
            {"horse_number": 5, "horse_name": "HORSE FIVE", "probability_winner": 0.07, "predicted_rank": 5},
        ],
    }
    prediction.update(overrides)
    return prediction


class LiveMarketComparisonTests(unittest.TestCase):
    def test_compares_only_pre_race_probabilities_with_verified_prices(self):
        report = build_comparison(valid_prediction(), valid_snapshot())
        self.assertIsNotNone(report)
        self.assertEqual(report["race_key"], "2026-10-12|MARSEILLE-BORELY|4")
        self.assertEqual(report["runner_count"], 5)
        shares = [row["normalized_market_share"] for row in report["runner_comparison"]]
        self.assertAlmostEqual(sum(shares), 1.0, places=10)
        self.assertTrue(all("model_minus_market_share" in row for row in report["runner_comparison"]))
        self.assertTrue(report["research_only"])
        self.assertFalse(report["real_money_authorized"])
        self.assertFalse(report["roi_claim_permitted"])

    def test_race_normalizes_independent_winner_estimates_before_market_comparison(self):
        prediction = valid_prediction(ranked_horses=[
            {"horse_number": 1, "horse_name": "HORSE ONE", "probability_winner": 0.50, "predicted_rank": 1},
            {"horse_number": 2, "horse_name": "HORSE TWO", "probability_winner": 0.40, "predicted_rank": 2},
            {"horse_number": 3, "horse_name": "HORSE THREE", "probability_winner": 0.30, "predicted_rank": 3},
            {"horse_number": 4, "horse_name": "HORSE FOUR", "probability_winner": 0.20, "predicted_rank": 4},
            {"horse_number": 5, "horse_name": "HORSE FIVE", "probability_winner": 0.10, "predicted_rank": 5},
        ])
        report = build_comparison(prediction, valid_snapshot())

        self.assertIsNotNone(report)
        self.assertAlmostEqual(report["model_probability_sum_before_normalization"], 1.50, places=8)
        self.assertAlmostEqual(report["model_probability_sum_after_normalization"], 1.0, places=10)
        first = next(row for row in report["runner_comparison"] if row["horse_number"] == 1)
        self.assertAlmostEqual(first["raw_model_probability_winner"], 0.50, places=8)
        self.assertAlmostEqual(first["model_probability_winner"], 0.50 / 1.50, places=8)
        self.assertAlmostEqual(
            first["model_minus_market_share"],
            first["model_probability_winner"] - first["normalized_market_share"],
            places=8,
        )
        self.assertTrue(report["research_only"])
        self.assertFalse(report["real_money_authorized"])

    def test_uses_saved_raw_win_estimates_when_prediction_also_has_normalized_values(self):
        raw = [0.50, 0.40, 0.30, 0.20, 0.10]
        total = sum(raw)
        prediction = valid_prediction(ranked_horses=[
            {
                "horse_number": number,
                "horse_name": f"HORSE {number}",
                "probability_winner": value / total,
                "raw_probability_winner": value,
                "predicted_rank": index,
            }
            for index, (number, value) in enumerate(zip(range(1, 6), raw), start=1)
        ])

        report = build_comparison(prediction, valid_snapshot())

        self.assertIsNotNone(report)
        self.assertAlmostEqual(report["model_probability_sum_before_normalization"], total, places=8)
        self.assertAlmostEqual(report["model_probability_sum_after_normalization"], 1.0, places=10)
        first = next(row for row in report["runner_comparison"] if row["horse_number"] == 1)
        self.assertAlmostEqual(first["raw_model_probability_winner"], 0.50, places=8)
        self.assertAlmostEqual(first["model_probability_winner"], 0.50 / total, places=8)

    def test_never_converts_no_bet_into_a_bet(self):
        prediction = valid_prediction(live_decision="NO_BET", recommended_numbers=[])
        report = build_comparison(prediction, valid_snapshot())
        self.assertIsNotNone(report)
        self.assertEqual(report["live_decision"], "NO_BET")
        self.assertEqual(report["recommended_numbers"], [])
        self.assertTrue(report["decision_policy_preserved"])

    def test_rejects_mismatched_race_keys(self):
        report = build_comparison(valid_prediction(), valid_snapshot(race_key="2026-10-12|AUTEUIL|1"))
        self.assertIsNone(report)

    def test_rejects_prediction_generated_after_price_snapshot(self):
        prediction = valid_prediction(generated_at="2026-10-12T02:08:00+00:00")
        report = build_comparison(prediction, valid_snapshot())
        self.assertIsNone(report)

    def test_rejects_post_off_market_snapshot(self):
        snapshot = valid_snapshot(
            captured_at="2026-10-12T11:56:00+00:00",
            price_timestamp="2026-10-12T11:56:00+00:00",
        )
        self.assertIsNone(build_comparison(valid_prediction(), snapshot))

    def test_attaches_only_verified_settlement_and_scores_full_field(self):
        comparison = build_comparison(valid_prediction(), valid_snapshot())
        evaluation = {
            "race_key": "2026-10-12|MARSEILLE-BORELY|4",
            "status": "result_verified",
            "verified_at": "2026-10-12T12:20:00+00:00",
            "result": {"winner": 3, "arrival": [3, 1, 2]},
            "result_validation": {"accepted_for_learning": True, "reason": "validated_against_program_roster"},
        }

        settled = build_settlement_metrics(comparison, evaluation)
        self.assertIsNotNone(settled)
        self.assertEqual(settled["winner_number"], 3)
        self.assertTrue(settled["winner_in_model_top3"])
        self.assertTrue(settled["winner_in_market_top3"])
        self.assertTrue(settled["full_field_probability_metrics_available"])
        self.assertIsNotNone(settled["model_multiclass_brier_score"])
        self.assertIsNotNone(settled["market_multiclass_brier_score"])
        self.assertTrue(settled["research_only"])
        self.assertFalse(settled["real_money_authorized"])
        self.assertFalse(settled["roi_claim_permitted"])

    def test_result_verification_must_not_precede_race_off_time(self):
        comparison = build_comparison(valid_prediction(), valid_snapshot())
        evaluation = {
            "race_key": "2026-10-12|MARSEILLE-BORELY|4",
            "status": "result_verified",
            "verified_at": "2026-10-12T11:54:00+00:00",
            "result": {"winner": 3},
            "result_validation": {"accepted_for_learning": True},
        }
        self.assertIsNone(build_settlement_metrics(comparison, evaluation))

    def test_unaccepted_or_unsettled_result_cannot_update_comparison(self):
        comparison = build_comparison(valid_prediction(), valid_snapshot())
        rejected = {
            "race_key": "2026-10-12|MARSEILLE-BORELY|4",
            "status": "result_verified",
            "result": {"winner": 3},
            "result_validation": {"accepted_for_learning": False},
        }
        self.assertIsNone(build_settlement_metrics(comparison, rejected))
        rejected["result_validation"]["accepted_for_learning"] = True
        rejected["status"] = "pending"
        self.assertIsNone(build_settlement_metrics(comparison, rejected))

    def test_partial_field_must_not_emit_probability_error_scores(self):
        comparison = build_comparison(
            valid_prediction(),
            valid_snapshot(odds={"1": 3.0, "2": 5.0, "3": 10.0, "4": 20.0}),
        )
        self.assertIsNotNone(comparison)
        evaluation = {
            "race_key": "2026-10-12|MARSEILLE-BORELY|4",
            "status": "result_verified",
            "verified_at": "2026-10-12T12:20:00+00:00",
            "result": {"winner": 3},
            "result_validation": {"accepted_for_learning": True},
        }
        settled = build_settlement_metrics(comparison, evaluation)
        self.assertIsNotNone(settled)
        self.assertFalse(settled["full_field_probability_metrics_available"])
        self.assertIsNone(settled["market_rank_of_winner"])
        self.assertIsNone(settled["winner_in_market_top3"])
        self.assertIsNone(settled["model_multiclass_brier_score"])
        self.assertIsNone(settled["market_multiclass_brier_score"])

    def test_rejects_insufficient_price_coverage(self):
        snapshot = valid_snapshot(odds={"1": 3.0, "2": 5.0, "3": 10.0})
        self.assertIsNone(build_comparison(valid_prediction(), snapshot))


if __name__ == "__main__":
    unittest.main()
