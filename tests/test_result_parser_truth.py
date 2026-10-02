import unittest

from src.parsers.results_parser import extract_arrival_from_line


class ResultParserTruthTests(unittest.TestCase):
    def test_payout_numbers_are_not_treated_as_horses(self):
        result = extract_arrival_from_line("4e 1 - 4 - 3 - 700 - 64 - 5 - 650 - 2328")
        self.assertIsNotNone(result)
        self.assertEqual(result["race_number"], 4)
        self.assertEqual(result["arrival"], [1, 4, 3])

    def test_normal_arrival_is_preserved(self):
        result = extract_arrival_from_line("1ère 13 - 8 - 10 - 1 - 5")
        self.assertEqual(result["arrival"], [13, 8, 10, 1, 5])


if __name__ == "__main__":
    unittest.main()
