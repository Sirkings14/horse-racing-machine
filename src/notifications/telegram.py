from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[2]
V3_PREDICTION_FILE = BASE_DIR / "data" / "model" / "latest_v3_prediction.json"


def _load_prediction() -> dict | None:
    """Load only the V4 evidence artifact; never fall back to legacy output."""
    if not V3_PREDICTION_FILE.exists():
        print("Telegram skipped: V4 evidence prediction artifact does not exist.")
        return None
    try:
        return json.loads(V3_PREDICTION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Telegram skipped: unreadable V4 prediction: {error}")
        return None


def send_latest_prediction() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram skipped: secrets are not configured.")
        return False

    payload = _load_prediction()
    if payload is None:
        return False

    if payload.get("mode") not in {"v3_evidence_no_press", "v5_market_opportunity_layer"}:
        print(f"Telegram skipped: unsupported prediction mode {payload.get('mode')!r}.")
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
        print(f"Telegram skipped: stale prediction for {parsed_race_date.isoformat()} (today is {today.isoformat()}).")
        return False

    ranked = payload.get("ranked_horses") or []
    candidates = [item.get("horse_number") for item in ranked[:5] if item.get("horse_number") is not None]
    if not candidates:
        candidates = payload.get("recommended_numbers") or []

    guard = payload.get("autopilot_guard") or {}
    decision = payload.get("live_decision")
    if not decision:
        decision = "NO_BET" if guard.get("decision") == "PASS" else "PLAY_CANDIDATE"

    race_key = payload.get("race_key") or "unknown"
    monitor = payload.get("monitoring") or {}
    agreement = monitor.get("agreement") or payload.get("model_agreement", "unknown")

    predicted_order = candidates
    order_top5 = []
    adaptive_depth = len(candidates)
    model_label = payload.get("model_version", "unknown")

    if decision == "NO_BET":
        reasons = guard.get("gate_reasons") or payload.get("no_bet_reason") or ["autopilot guard blocked live play"]
        lines = [
            "🏇 HORSE RACING MACHINE",
            "",
            f"Race: {race_key}",
            f"Track: {race.get('track')}",
            f"Race: {race.get('race_name') or 'N/A'}",
            f"Distance: {race.get('distance')}m",
            "🛑 NO BET — V4 evidence gate blocked live play",
            f"🧪 Model candidates (NOT CLEARED): {' - '.join(map(str, candidates))}",
            f"🧠 Model agreement: {agreement}",
            f"Model: {model_label}",
            "",
            "Gate reasons:",
            *[f"• {reason}" for reason in reasons],
            "",
            "⚠️ Candidates are model output only; they are not cleared betting recommendations.",
        ]
    else:
        lines = [
            "🏇 HORSE RACING MACHINE",
            "",
            f"Race: {race_key}",
            f"Track: {race.get('track')}",
            f"Race: {race.get('race_name') or 'N/A'}",
            f"Distance: {race.get('distance')}m",
            f"🎯 Recommended {len(candidates)}: {' - '.join(map(str, candidates))}",
            f"🏆 Predicted order: {' - '.join(map(str, predicted_order))}",
            "🔎 Order engine: unavailable in V4 evidence predictor",
            f"🧠 Model agreement: {agreement}",
            f"Adaptive depth: {adaptive_depth}",
            f"Model: {model_label}",
            "",
            "Race intelligence — Top 5:",
        ]

    for horse in ranked[:5]:
        probability = float(horse.get("probability_top3", 0))
        order_rank = horse.get("order_rank")
        position = horse.get("final_predicted_position", horse.get("predicted_rank", "?"))
        order_text = f" | Order #{order_rank}" if order_rank is not None else ""
        lines.append(
            f"{position}. {horse.get('horse_number')} {horse.get('horse_name')} "
            f"| Top3 {probability:.1%}{order_text}"
        )

    if decision != "NO_BET" and (monitor.get("warning") or payload.get("warning")):
        lines += ["", f"⚠️ {monitor.get('warning') or payload.get('warning')}"]

    lines += ["", "⚠️ Model output only. Horse racing remains uncertain."]

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
