import unittest

from src.model.value_engine import evaluate_market_value


class ValueEngineTests(unittest.TestCase):
    def test_positive_expected_value(self):
        result = evaluate_market_value(0.30, 4.0)
        self.assertAlmostEqual(result["implied_probability"], 0.25)
        self.assertAlmostEqual(result["expected_value"], 0.20)
        self.assertTrue(result["positive_value"])

    def test_negative_expected_value(self):
        result = evaluate_market_value(0.20, 4.0)
        self.assertAlmostEqual(result["expected_value"], -0.20)
        self.assertFalse(result["positive_value"])


if __name__ == "__main__":
    unittest.main()
