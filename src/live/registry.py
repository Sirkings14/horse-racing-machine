from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
LIVE_DIR = BASE_DIR / "data" / "live"
MANIFEST_FILE = LIVE_DIR / "live_manifest.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_FILE.exists():
        return {"version": 1, "updated_at": None, "races": []}
    try:
        payload = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "updated_at": None, "races": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("races"), list):
        return {"version": 1, "updated_at": None, "races": []}
    return payload


def _atomic_write(payload: dict[str, Any]):
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="live_manifest_", suffix=".tmp", dir=LIVE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, MANIFEST_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def upsert_race(race: dict[str, Any]) -> dict[str, Any]:
    payload = load_manifest()
    races = payload["races"]
    key = race.get("race_key")
    if not key:
        raise ValueError("Live registry race requires race_key")

    existing = next((item for item in races if item.get("race_key") == key), None)
    if existing is None:
        race.setdefault("status", "validated")
        race.setdefault("prediction_status", "pending")
        race.setdefault("result_status", "pending")
        race.setdefault("created_at", _now())
        race["updated_at"] = _now()
        races.append(race)
        result = race
    else:
        previous_status = existing.get("status", "validated")
        previous_prediction_status = existing.get("prediction_status", "pending")
        previous_result_status = existing.get("result_status", "pending")
        existing.update(race)
        existing["status"] = race.get("status", previous_status)
        existing["prediction_status"] = race.get("prediction_status", previous_prediction_status)
        existing["result_status"] = race.get("result_status", previous_result_status)
        existing.setdefault("created_at", _now())
        existing["updated_at"] = _now()
        result = existing

    races.sort(key=lambda item: (str(item.get("date") or "9999-99-99"), int(item.get("race_number") or 9999)))
    payload["version"] = 1
    payload["updated_at"] = _now()
    _atomic_write(payload)
    return result


def eligible_races(today_iso: str | None = None) -> list[dict[str, Any]]:
    payload = load_manifest()
    races = payload.get("races", [])
    result = []
    for race in races:
        if race.get("status") != "validated":
            continue
        if race.get("prediction_status") not in (None, "pending"):
            continue
        if race.get("result_status") == "verified":
            continue
        race_date = str(race.get("date") or "")[:10]
        if today_iso and race_date < today_iso:
            continue
        result.append(race)
    result.sort(key=lambda item: (str(item.get("date") or "9999-99-99"), int(item.get("race_number") or 9999)))
    return result


def mark_predicted(race_key: str, prediction_file: str):
    payload = load_manifest()
    for race in payload.get("races", []):
        if race.get("race_key") == race_key:
            race["prediction_status"] = "predicted"
            race["prediction_file"] = prediction_file
            race["predicted_at"] = _now()
            race["updated_at"] = _now()
            break
    payload["updated_at"] = _now()
    _atomic_write(payload)


def mark_result_verified(race_key: str, evaluation_file: str):
    payload = load_manifest()
    for race in payload.get("races", []):
        if race.get("race_key") == race_key:
            race["result_status"] = "verified"
            race["evaluation_file"] = evaluation_file
            race["result_verified_at"] = _now()
            race["updated_at"] = _now()
            break
    payload["updated_at"] = _now()
    _atomic_write(payload)
