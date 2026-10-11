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

    def test_ecd_payout_columns_after_top3_are_not_a_fourth_finisher(self):
        result = extract_arrival_from_line(
            "1ère 16 - 5 - 14 5 2 750 25 16 - 14 5 200 1856"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["arrival"], [16, 5, 14])

    def test_caen_payout_columns_do_not_extend_the_arrival(self):
        result = extract_arrival_from_line(
            "4ième 9 - 10 - 4 10 1 400 74 9 - 4 10 700 947"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["arrival"], [9, 10, 4])


if __name__ == "__main__":
    unittest.main()
