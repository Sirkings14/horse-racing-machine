import unittest

import numpy as np

from src.model.v3_model import normalize_race_probabilities


class RaceProbabilityNormalizationTests(unittest.TestCase):
    def test_returns_single_winner_distribution_and_preserves_relative_mass(self):
        raw = [0.50, 0.40, 0.10]
        normalized = normalize_race_probabilities(raw)

        self.assertTrue(np.all(np.isfinite(normalized)))
        self.assertAlmostEqual(float(normalized.sum()), 1.0, places=12)
        self.assertAlmostEqual(float(normalized[0]), 0.50, places=12)
        self.assertAlmostEqual(float(normalized[1]), 0.40, places=12)
        self.assertAlmostEqual(float(normalized[2]), 0.10, places=12)

    def test_normalizes_probability_mass_above_one(self):
        normalized = normalize_race_probabilities([0.50, 0.40, 0.30, 0.20, 0.10])
        self.assertAlmostEqual(float(normalized.sum()), 1.0, places=12)
        self.assertAlmostEqual(float(normalized[0]), 1.0 / 3.0, places=12)

    def test_rejects_zero_or_invalid_probability_mass(self):
        for values in ([], [0.0, 0.0], [-0.1, 0.5], [0.2, float("nan")], [0.2, 1.2]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    normalize_race_probabilities(values)

    def test_rejects_multidimensional_input(self):
        with self.assertRaises(ValueError):
            normalize_race_probabilities([[0.2, 0.3], [0.1, 0.4]])


if __name__ == "__main__":
    unittest.main()
