import unittest

from src.model.profitability import _economic_snapshot, evaluate_fixed_stake


class ProfitabilityTests(unittest.TestCase):
    def test_winner_return_and_roi(self):
        result = evaluate_fixed_stake([4, 13, 9, 6, 10], 4, {4: 5.0})
        self.assertEqual(result["stake"], 5.0)
        self.assertEqual(result["return"], 5.0)
        self.assertEqual(result["profit"], 0.0)
        self.assertEqual(result["roi"], 0.0)

    def test_no_price_means_no_return(self):
        result = evaluate_fixed_stake([4, 13, 9], 4, {})
        self.assertEqual(result["return"], 0.0)
        self.assertEqual(result["profit"], -3.0)

    def test_economic_gate_requires_verified_pre_race_provenance(self):
        base = {
            "observed": True,
            "evidence_grade": "verified_pre_race_market_odds",
            "source_type": "bookmaker_win",
            "source_url": "https://example.com/race/1",
            "captured_at": "2026-10-12T10:00:00Z",
            "price_timestamp": "2026-10-12T09:59:30Z",
            "race_off_at": "2026-10-12T10:15:00Z",
        }
        self.assertTrue(_economic_snapshot(base))
        self.assertFalse(_economic_snapshot({**base, "evidence_grade": "legacy"}))
        self.assertFalse(_economic_snapshot({**base, "captured_at": "2026-10-12T10:16:00Z"}))
        self.assertFalse(_economic_snapshot({**base, "source_type": "press_estimate"}))


if __name__ == "__main__":
    unittest.main()
