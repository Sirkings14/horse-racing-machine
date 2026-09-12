from __future__ import annotations
import json, os
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
    payload = json.loads(PREDICTION_FILE.read_text(encoding="utf-8"))
    if payload.get("mode") != "future_or_unmatched":
        print("Telegram skipped: latest prediction is retrospective.")
        return False
    race = payload.get("race") or {}
    numbers = payload.get("recommended_numbers") or []
    lines = ["🏇 HORSE RACING MACHINE","",f"Race: {payload.get('race_key')}",
        f"Track: {race.get('track')}",f"Distance: {race.get('distance')}m",
        f"🎯 Recommended {len(numbers)}: {' - '.join(map(str,numbers))}",
        f"Adaptive depth: {payload.get('adaptive_top_count',len(numbers))}","","Top ranked:"]
    for horse in (payload.get("ranked_horses") or [])[:5]:
        lines.append(f"{horse.get('predicted_rank')}. {horse.get('horse_number')} {horse.get('horse_name')} | {float(horse.get('probability_top3',0)):.1%}")
    lines += ["","⚠️ Model output only. Horse racing remains uncertain."]
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id":chat_id,"text":"\n".join(lines)},timeout=30)
    response.raise_for_status()
    print("Prediction sent to Telegram.")
    return True

if __name__ == "__main__":
    send_latest_prediction()
