import unittest

from src.model.v3_scoring import rank_disagreement, rank_percentiles, weighted_outcome_score


class V3ScoringTests(unittest.TestCase):
    def test_live_and_backtest_share_the_same_weighted_score(self):
        self.assertAlmostEqual(weighted_outcome_score(0.2, 0.5, 0.8), 0.5)
        self.assertAlmostEqual(
            weighted_outcome_score(0.35, 0.35, 0.35),
            0.35,
        )

    def test_probability_scale_differences_do_not_create_false_disagreement(self):
        numbers = [1, 2, 3]
        winner = [0.35, 0.10, 0.02]
        top3 = [0.92, 0.55, 0.11]
        top5 = [0.99, 0.83, 0.40]
        disagreement = rank_disagreement((winner, top3, top5), numbers)
        self.assertEqual(disagreement, [0.0, 0.0, 0.0])

    def test_different_model_orders_create_rank_disagreement(self):
        numbers = [1, 2, 3]
        winner = [0.90, 0.50, 0.10]
        top3 = [0.10, 0.50, 0.90]
        top5 = [0.90, 0.50, 0.10]
        disagreement = rank_disagreement((winner, top3, top5), numbers)
        self.assertGreater(disagreement[0], 0.4)
        self.assertEqual(disagreement[1], 0.0)
        self.assertGreater(disagreement[2], 0.4)

    def test_rank_percentile_ties_are_deterministic_by_horse_number(self):
        self.assertEqual(rank_percentiles([0.5, 0.5, 0.1], [8, 2, 5]), [0.5, 0.0, 1.0])

    def test_invalid_or_mismatched_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            weighted_outcome_score(float("nan"), 0.5, 0.7)
        with self.assertRaises(ValueError):
            rank_percentiles([0.4], [1, 2])


if __name__ == "__main__":
    unittest.main()
