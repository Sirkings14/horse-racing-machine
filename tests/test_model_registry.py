from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.model import model_registry


class ModelRegistryPersistenceTests(unittest.TestCase):
    def test_promotion_decision_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_file = root / "model_registry.json"
            with patch.object(model_registry, "REGISTRY_FILE", registry_file),                  patch.object(model_registry, "MODEL_DIR", root):
                model_registry.record_promotion_decision(
                    "model-test",
                    "shadow",
                    "test_persistence",
                    {"winner_hit_rate_at_3": 0.42},
                )

                payload = json.loads(registry_file.read_text(encoding="utf-8"))
                entry = payload["promotion_ledger"][0]

                self.assertEqual(entry["version"], "model-test")
                self.assertEqual(entry["decision"], "shadow")
                self.assertEqual(entry["metrics"]["winner_hit_rate_at_3"], 0.42)
                self.assertIn("updated_at", payload)



# CI trigger marker: registry persistence is covered by the workflow regression suite.

if __name__ == "__main__":
    unittest.main()
