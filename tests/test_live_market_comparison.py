import unittest

from src.model.live_market_comparison import build_comparison


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

    def test_rejects_insufficient_price_coverage(self):
        snapshot = valid_snapshot(odds={"1": 3.0, "2": 5.0, "3": 10.0})
        self.assertIsNone(build_comparison(valid_prediction(), snapshot))


if __name__ == "__main__":
    unittest.main()
