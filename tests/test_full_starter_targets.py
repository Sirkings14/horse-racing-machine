import unittest

from scripts.build_historical_dataset import (
    _arrival_positions,
    _eligible_training_races,
    _target_fields,
)


class FullStarterTargetTests(unittest.TestCase):
    def test_arrival_parser_preserves_dead_heat_competition_ranks(self):
        positions = _arrival_positions("[[7], [2, 4], [8], [5], [1]]")
        self.assertEqual(positions, {7: 1, 2: 2, 4: 2, 8: 4, 5: 5, 1: 6})

    def test_arrival_parser_fails_closed_on_malformed_or_unusable_truth(self):
        self.assertIsNone(_arrival_positions(None))
        self.assertIsNone(_arrival_positions("[[1], [2]]"))
        self.assertIsNone(_arrival_positions("[[1], [2], [2]]"))
        self.assertIsNone(_arrival_positions("[[1], ['OCR'], [3]]"))

    def test_unplaced_starter_is_a_negative_topn_example_not_a_fake_finish(self):
        targets = _target_fields(18, {7: 1, 2: 2, 4: 2, 8: 4, 5: 5, 1: 6})
        self.assertIsNone(targets["finish_position"])
        self.assertEqual(targets["won"], 0)
        self.assertEqual(targets["top3"], 0)
        self.assertEqual(targets["top5"], 0)

    def test_dead_heat_members_share_rank_and_topn_labels(self):
        targets = _target_fields(4, {7: 1, 2: 2, 4: 2, 8: 4, 5: 5, 1: 6})
        self.assertEqual(targets["finish_position"], 2)
        self.assertEqual(targets["top3"], 1)
        self.assertEqual(targets["top5"], 1)

    def test_only_finalized_complete_unambiguous_rosters_are_training_eligible(self):
        meta = {
            "complete": {
                "arrival_definitive": True,
                "arrival_positions": {1: 1, 2: 2, 3: 3},
                "runners_count": 4,
            },
            "provisional": {
                "arrival_definitive": False,
                "arrival_positions": {1: 1, 2: 2, 3: 3},
                "runners_count": 4,
            },
            "short_roster": {
                "arrival_definitive": True,
                "arrival_positions": {1: 1, 2: 2, 3: 3},
                "runners_count": 4,
            },
            "unknown_finisher": {
                "arrival_definitive": True,
                "arrival_positions": {1: 1, 2: 2, 99: 3},
                "runners_count": 4,
            },
        }
        counts = {"complete": 4, "provisional": 4, "short_roster": 3, "unknown_finisher": 4}
        numbers = {
            "complete": {1, 2, 3, 4},
            "provisional": {1, 2, 3, 4},
            "short_roster": {1, 2, 3},
            "unknown_finisher": {1, 2, 3, 4},
        }
        eligible, audit = _eligible_training_races(meta, counts, numbers, set())
        self.assertEqual(eligible, {"complete"})
        self.assertEqual(audit["non_finalized_races"], 1)
        self.assertEqual(audit["incomplete_or_duplicate_rosters"], 1)
        self.assertEqual(audit["arrival_numbers_outside_roster"], 1)


if __name__ == "__main__":
    unittest.main()
