from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "data" / "model"
REGISTRY_FILE = MODEL_DIR / "model_registry.json"
BACKTEST_FILE = MODEL_DIR / "backtest_report.json"
ORDER_BACKTEST_FILE = MODEL_DIR / "order_backtest_report.json"
LEDGER_FILE = MODEL_DIR / "model_evolution_ledger.json"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def record_evolution(version: str) -> dict[str, Any]:
    registry = _load(REGISTRY_FILE, {})
    backtest = _load(BACKTEST_FILE, {})
    order_backtest = _load(ORDER_BACKTEST_FILE, {})
    history = _load(LEDGER_FILE, [])
    if not isinstance(history, list):
        history = []

    metrics = backtest.get("metrics") or {}
    order_metrics = order_backtest.get("metrics") or {}
    champion = registry.get("champion_version")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate_version": version,
        "champion_version": champion,
        "candidate": {
            "standard_metrics": metrics,
            "order_metrics": order_metrics,
            "backtest_method": backtest.get("method"),
            "order_backtest_method": order_backtest.get("method"),
        },
        "decision": "pending_promotion",
    }

    history.append(entry)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(history[-200:], indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def main(version: str | None = None) -> dict[str, Any]:
    if not version:
        version = "unknown"
    result = record_evolution(version)
    print(f"MODEL EVOLUTION: recorded {version}")
    return result


if __name__ == "__main__":
    main()
