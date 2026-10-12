import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.model import predict_v3


class PreraceProgramSelectionTests(unittest.TestCase):
    def setUp(self):
        self.races = [
            {"race_key": "2026-10-11|AUTEUIL|3", "structured_file": "structured/today.json"},
            {"race_key": "2026-10-12|MARSEILLE-BORELY|4", "structured_file": "structured/tomorrow.json"},
        ]
        self.programs = {
            "today.json": {"date": "2026-10-11", "published_arrival": [8, 13, 12, 7, 4]},
            "tomorrow.json": {"date": "2026-10-12", "published_arrival": []},
        }
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.predictions_dir = Path(self.temp_dir.name) / "predictions"
        self.predictions_dir.mkdir()
        self.ledger_file = Path(self.temp_dir.name) / "telegram_delivery_ledger.json"

    def _write_notified_snapshot(
        self,
        horse_numbers,
        race_key="2026-10-11|AUTEUIL|3",
        program_key="today.json",
        generated_at="2026-10-11T16:21:42.327711+00:00",
        sent_at="2026-10-11T16:21:42.705918+00:00",
    ):
        reasons = ["economic_validation_unavailable", "insufficient_verified_history"]
        program = self.programs[program_key]
        payload = {
            "generated_at": generated_at,
            "race_key": race_key,
            "mode": "v5_market_opportunity_layer",
            "live_decision": "NO_BET",
            "ranked_horses": [{"horse_number": number} for number in horse_numbers],
            "autopilot_guard": {"decision": "PASS", "gate_reasons": reasons},
            "source_program_fingerprint": predict_v3._program_fingerprint(program),
            "model_fingerprint": "test-model-fingerprint",
        }
        safe_key = race_key.replace("|", "_")
        (self.predictions_dir / f"{safe_key}_v3.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        signature = {
            "decision": "NO_BET",
            "candidates_in_order": [int(number) for number in horse_numbers],
            "gate_reasons": sorted(reasons),
        }
        self.ledger_file.write_text(
            json.dumps({
                "schema_version": 1,
                "notifications": {
                    race_key: {
                        "signature": signature,
                        "sent_at": sent_at,
                        "prediction_id": "test-prediction",
                        "model_version": "v4-evidence-no-press",
                        "telegram_message_id": 235,
                    }
                },
            }),
            encoding="utf-8",
        )

    def _fake_load(self, path):
        return self.programs[path.name]

    def test_skips_race_with_published_arrival_and_selects_next_race(self):
        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertEqual(entry["race_key"], "2026-10-12|MARSEILLE-BORELY|4")
        self.assertEqual(program["date"], "2026-10-12")

    def test_returns_none_when_every_candidate_has_published_arrival(self):
        self.programs["tomorrow.json"]["published_arrival"] = [3, 4, 1]
        with patch.object(predict_v3, "_json", side_effect=self._fake_load):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertIsNone(entry)
        self.assertIsNone(program)

    def test_selects_first_race_when_no_arrival_is_published(self):
        self.programs["today.json"]["published_arrival"] = []
        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")

    def test_skips_identical_same_day_snapshot_after_confirmed_telegram_delivery(self):
        self.programs["today.json"]["published_arrival"] = []
        self._write_notified_snapshot([1, 16, 14, 13, 2])

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertEqual(entry["race_key"], "2026-10-12|MARSEILLE-BORELY|4")
        self.assertEqual(program["date"], "2026-10-12")

    def test_keeps_same_day_race_eligible_when_snapshot_changes_for_update(self):
        self.programs["today.json"]["published_arrival"] = []
        self._write_notified_snapshot([1, 16, 14, 13, 2])
        snapshot_path = self.predictions_dir / "2026-10-11_AUTEUIL_3_v3.json"
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        payload["ranked_horses"] = [{"horse_number": number} for number in [5, 16, 14, 13, 2]]
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")

    def test_keeps_same_day_race_eligible_when_delivery_was_not_confirmed(self):
        self.programs["today.json"]["published_arrival"] = []
        snapshot_path = self.predictions_dir / "2026-10-11_AUTEUIL_3_v3.json"
        snapshot_path.write_text(json.dumps({
            "generated_at": "2026-10-11T16:21:42.327711+00:00",
            "live_decision": "NO_BET",
            "ranked_horses": [{"horse_number": number} for number in [1, 16, 14, 13, 2]],
            "autopilot_guard": {
                "decision": "PASS",
                "gate_reasons": ["economic_validation_unavailable", "insufficient_verified_history"],
            },
        }), encoding="utf-8")

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(self.races, model_fingerprint="test-model-fingerprint")

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")

    def test_skips_future_race_notified_the_day_before_when_card_and_model_match(self):
        self.programs["today.json"]["published_arrival"] = [8, 13, 12, 7, 4]
        self._write_notified_snapshot(
            [2, 5, 13, 8, 1],
            race_key="2026-10-12|MARSEILLE-BORELY|4",
            program_key="tomorrow.json",
            generated_at="2026-10-11T23:33:30+00:00",
            sent_at="2026-10-11T23:33:30+00:00",
        )

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(
                self.races, model_fingerprint="test-model-fingerprint"
            )

        self.assertIsNone(entry)
        self.assertIsNone(program)

    def test_same_race_is_recomputed_when_card_fingerprint_changes(self):
        self.programs["today.json"]["published_arrival"] = []
        self._write_notified_snapshot([1, 16, 14, 13, 2])
        self.programs["today.json"]["source_sha256"] = "new-program-sha"

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(
                self.races, model_fingerprint="test-model-fingerprint"
            )

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")

    def test_same_race_is_recomputed_when_model_fingerprint_changes(self):
        self.programs["today.json"]["published_arrival"] = []
        self._write_notified_snapshot([1, 16, 14, 13, 2])

        with patch.object(predict_v3, "_json", side_effect=self._fake_load), \
             patch.object(predict_v3, "PREDICTIONS_DIR", self.predictions_dir), \
             patch.object(predict_v3, "NOTIFICATION_LEDGER_FILE", self.ledger_file):
            entry, program = predict_v3._first_unfinished_program(
                self.races, model_fingerprint="different-model-fingerprint"
            )

        self.assertEqual(entry["race_key"], "2026-10-11|AUTEUIL|3")
        self.assertEqual(program["date"], "2026-10-11")



if __name__ == "__main__":
    unittest.main()
