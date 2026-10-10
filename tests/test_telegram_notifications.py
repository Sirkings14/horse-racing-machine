import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.notifications import telegram


class TelegramDeliveryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.tempdir.name) / "telegram_delivery_ledger.json"
        self.today = datetime.now(timezone.utc).date().isoformat()
        self.payload = {
            "prediction_id": "test-prediction-1",
            "mode": "v5_market_opportunity_layer",
            "model_version": "test-model",
            "race_key": f"{self.today}|AUTEUIL|1",
            "race": {"date": self.today, "track": "AUTEUIL", "race_number": 1,
                     "race_name": "TEST RACE", "distance": 3600},
            "live_decision": "NO_BET",
            "autopilot_guard": {"decision": "PASS",
                                "gate_reasons": ["economic_validation_unavailable"]},
            "ranked_horses": [
                {"horse_number": 7, "horse_name": "CHEVAL A", "probability_top3": 0.35},
                {"horse_number": 2, "horse_name": "CHEVAL B", "probability_top3": 0.30},
                {"horse_number": 5, "horse_name": "CHEVAL C", "probability_top3": 0.25},
            ],
            "recommended_numbers": [7, 2, 5],
            "monitoring": {"agreement": "low"},
        }

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def configure_post(post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        post.return_value = response

    def test_identical_prediction_is_sent_only_once(self):
        with (
            patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"}),
            patch.object(telegram, "LEDGER_FILE", self.ledger_path),
            patch.object(telegram, "_load_prediction", return_value=self.payload),
            patch("src.notifications.telegram.requests.post") as post,
        ):
            self.configure_post(post)
            self.assertTrue(telegram.send_latest_prediction())
            self.assertFalse(telegram.send_latest_prediction())
            self.assertEqual(post.call_count, 1)
        ledger = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        entry = ledger["notifications"][self.payload["race_key"]]
        self.assertEqual(entry["telegram_message_id"], 123)
        self.assertEqual(entry["signature"]["candidates_in_order"], [7, 2, 5])

    def test_changed_candidate_order_sends_an_update(self):
        changed = dict(self.payload)
        changed["mode"] = "v4_evidence_no_press"
        changed["ranked_horses"] = [
            {"horse_number": 2, "horse_name": "CHEVAL B", "probability_top3": 0.31},
            {"horse_number": 7, "horse_name": "CHEVAL A", "probability_top3": 0.30},
        ]
        with (
            patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"}),
            patch.object(telegram, "LEDGER_FILE", self.ledger_path),
            patch.object(telegram, "_load_prediction", side_effect=[self.payload, changed]),
            patch("src.notifications.telegram.requests.post") as post,
        ):
            self.configure_post(post)
            self.assertTrue(telegram.send_latest_prediction())
            self.assertTrue(telegram.send_latest_prediction())
            self.assertEqual(post.call_count, 2)

    def test_api_ok_false_does_not_record_delivery(self):
        with (
            patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"}),
            patch.object(telegram, "LEDGER_FILE", self.ledger_path),
            patch.object(telegram, "_load_prediction", return_value=self.payload),
            patch("src.notifications.telegram.requests.post") as post,
        ):
            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {"ok": False, "description": "chat not found"}
            post.return_value = response
            with self.assertRaisesRegex(RuntimeError, "did not confirm delivery"):
                telegram.send_latest_prediction()
        self.assertFalse(self.ledger_path.exists())


if __name__ == "__main__":
    unittest.main()
