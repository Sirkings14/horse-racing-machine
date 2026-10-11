import unittest

from scripts.audit_open_pmu_cotes import audit_payload


class OpenPmuCotesAuditTests(unittest.TestCase):
    def test_reports_cotes_as_exploratory_only_and_counts_timestamps(self):
        payload = {
            "message": [{
                "arrivee_details": {
                    "1": {"nom_cheval": "A", "cotes": [9.8, 8.5, 6.1]},
                    "2": {"nom_cheval": "B", "cotes": ["4.0", "3.7", "3.3"], "price_timestamp": "ignored"},
                    "3": {"nom_cheval": "C"},
                }
            }]
        }
        report = audit_payload(payload)
        self.assertEqual(report["race_count"], 1)
        self.assertEqual(report["runner_rows_in_arrivee_details"], 3)
        self.assertEqual(report["runner_rows_with_cotes_array"], 2)
        self.assertEqual(report["cotes_array_length_distribution"], {3: 2})
        self.assertEqual(report["runner_rows_with_explicit_price_timestamp_field"], 1)
        self.assertEqual(report["decision"], "EXPLORATORY_ONLY_NOT_PRE_RACE_EVIDENCE")

    def test_empty_payload_does_not_invent_odds(self):
        report = audit_payload({"message": []})
        self.assertEqual(report["runner_rows_with_cotes_array"], 0)
        self.assertEqual(report["sample_cotes_arrays"], [])
        self.assertIn("NOT_PRE_RACE_EVIDENCE", report["decision"])


if __name__ == "__main__":
    unittest.main()
