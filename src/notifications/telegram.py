from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTION_FILE = BASE_DIR / "data" / "model" / "latest_prediction.json"


def send_latest_prediction() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram skipped: secrets are not configured.")
        return False

    if not PREDICTION_FILE.exists():
        print("Telegram skipped: prediction file does not exist.")
        return False

    try:
        payload = json.loads(PREDICTION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Telegram skipped: unreadable prediction file: {error}")
        return False

    if payload.get("mode") != "live_registry_prediction":
        print(
            "Telegram skipped: latest prediction is not a validated live-registry prediction."
        )
        return False

    race = payload.get("race") or {}
    race_date = str(race.get("date") or payload.get("today") or "")[:10]
    try:
        parsed_race_date = date.fromisoformat(race_date)
    except ValueError:
        print("Telegram skipped: prediction has an invalid race date.")
        return False

    today = datetime.now(timezone.utc).date()
    if parsed_race_date < today:
        print(
            f"Telegram skipped: stale prediction for {parsed_race_date.isoformat()} "
            f"(today is {today.isoformat()})."
        )
        return False

    numbers = payload.get("recommended_numbers") or []
    if not numbers:
        print("Telegram skipped: prediction contains no recommended numbers.")
        return False

    race_key = payload.get("race_key") or "unknown"
    lines = [
        "🏇 HORSE RACING MACHINE",
        "",
        f"Race: {race_key}",
        f"Track: {race.get('track')}",
        f"Race: {race.get('race_name') or 'N/A'}",
        f"Distance: {race.get('distance')}m",
        f"🎯 Recommended {len(numbers)}: {' - '.join(map(str, numbers))}",
        f"Adaptive depth: {payload.get('adaptive_top_count', len(numbers))}",
        f"Model: {payload.get('model_version', 'unknown')}",
        "",
        "Top ranked:",
    ]

    for horse in (payload.get("ranked_horses") or [])[:5]:
        probability = float(horse.get("probability_top3", 0))
        lines.append(
            f"{horse.get('predicted_rank')}. {horse.get('horse_number')} "
            f"{horse.get('horse_name')} | {probability:.1%}"
        )

    lines += [
        "",
        "⚠️ Model output only. Horse racing remains uncertain.",
    ]

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "\n".join(lines)},
        timeout=30,
    )
    response.raise_for_status()
    print("Prediction sent to Telegram.")
    return True


if __name__ == "__main__":
    send_latest_prediction()
