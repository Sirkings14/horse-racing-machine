import unittest

from src.model.profitability import evaluate_fixed_stake


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


if __name__ == "__main__":
    unittest.main()
