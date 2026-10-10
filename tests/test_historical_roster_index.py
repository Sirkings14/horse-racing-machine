import unittest

from scripts.build_historical_dataset import _validated_historical_rosters


class HistoricalRosterIndexTests(unittest.TestCase):
    def test_only_exact_declared_field_matches_are_kept(self):
        candidates = {
            "2024-04-01|AUTEUIL|1": {
                "raw-key-1": {"expected_count": 4, "horse_numbers": {1, 2, 3, 4}},
            },
            "2024-04-01|AUTEUIL|2": {
                "raw-key-2": {"expected_count": 4, "horse_numbers": {1, 2, 3}},
            },
        }
        rosters, stats = _validated_historical_rosters(candidates)

        self.assertEqual(rosters["2024-04-01|AUTEUIL|1"]["horse_numbers"], [1, 2, 3, 4])
        self.assertNotIn("2024-04-01|AUTEUIL|2", rosters)
        self.assertEqual(stats["validated_rosters"], 1)
        self.assertEqual(stats["runner_count_mismatches"], 1)
        self.assertNotIn("arrival", rosters["2024-04-01|AUTEUIL|1"])
        self.assertNotIn("won", rosters["2024-04-01|AUTEUIL|1"])

    def test_conflicting_complete_sources_are_marked_not_merged(self):
        candidates = {
            "2024-04-01|AUTEUIL|1": {
                "raw-key-a": {"expected_count": 4, "horse_numbers": {1, 2, 3, 4}},
                "raw-key-b": {"expected_count": 4, "horse_numbers": {1, 2, 3, 5}},
            }
        }
        rosters, stats = _validated_historical_rosters(candidates)

        self.assertTrue(rosters["2024-04-01|AUTEUIL|1"]["conflict"])
        self.assertEqual(rosters["2024-04-01|AUTEUIL|1"]["horse_numbers"], [])
        self.assertEqual(stats["conflicting_complete_rosters"], 1)

    def test_identical_complete_sources_collapse_deterministically(self):
        candidates = {
            "2024-04-01|AUTEUIL|1": {
                "raw-key-b": {"expected_count": 3, "horse_numbers": {3, 1, 2}},
                "raw-key-a": {"expected_count": 3, "horse_numbers": {2, 3, 1}},
            }
        }
        rosters, stats = _validated_historical_rosters(candidates)
        self.assertEqual(rosters["2024-04-01|AUTEUIL|1"]["horse_numbers"], [1, 2, 3])
        self.assertEqual(rosters["2024-04-01|AUTEUIL|1"]["source_meta_keys"], ["raw-key-a", "raw-key-b"])
        self.assertEqual(stats["validated_rosters"], 1)
        self.assertEqual(stats["conflicting_complete_rosters"], 0)


if __name__ == "__main__":
    unittest.main()
