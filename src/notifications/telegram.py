from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[2]
LEGACY_PREDICTION_FILE = BASE_DIR / "data" / "model" / "latest_prediction.json"
V3_PREDICTION_FILE = BASE_DIR / "data" / "model" / "latest_v3_prediction.json"


def _load_prediction() -> tuple[dict | None, bool]:
    """Prefer the V3 evidence artifact; never silently fall back to stale V2 data."""
    if V3_PREDICTION_FILE.exists():
        try:
            return json.loads(V3_PREDICTION_FILE.read_text(encoding="utf-8")), True
        except (OSError, json.JSONDecodeError) as error:
            print(f"Telegram skipped: unreadable V3 prediction: {error}")
            return None, True

    if LEGACY_PREDICTION_FILE.exists():
        try:
            return json.loads(LEGACY_PREDICTION_FILE.read_text(encoding="utf-8")), False
        except (OSError, json.JSONDecodeError) as error:
            print(f"Telegram skipped: unreadable legacy prediction: {error}")
            return None, False

    return None, False


def send_latest_prediction() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram skipped: secrets are not configured.")
        return False

    payload, is_v3 = _load_prediction()
    if payload is None:
        print("Telegram skipped: no usable prediction artifact exists.")
        return False

    if is_v3:
        if payload.get("mode") != "v3_evidence_no_press":
            print("Telegram skipped: V3 artifact has an unexpected mode.")
            return False
    elif payload.get("mode") != "live_registry_prediction":
        print("Telegram skipped: legacy prediction is not a validated live-registry prediction.")
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
    if is_v3 and not decision:
        decision = "NO_BET" if guard.get("decision") == "PASS" else "PLAY_CANDIDATE"

    race_key = payload.get("race_key") or "unknown"
    monitor = payload.get("monitoring") or {}
    agreement = monitor.get("agreement") or payload.get("model_agreement", "unknown")

    if is_v3:
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
    else:
        numbers = payload.get("recommended_numbers") or []
        if not numbers:
            print("Telegram skipped: legacy prediction contains no recommended numbers.")
            return False
        predicted_order = payload.get("predicted_finish_order") or []
        order_top5 = payload.get("order_engine_top5") or []
        adaptive_depth = payload.get("adaptive_top_count", len(numbers))
        model_label = payload.get("model_version", "unknown")
        lines = [
            "🏇 HORSE RACING MACHINE",
            "",
            f"Race: {race_key}",
            f"Track: {race.get('track')}",
            f"Race: {race.get('race_name') or 'N/A'}",
            f"Distance: {race.get('distance')}m",
            f"🎯 Recommended {len(numbers)}: {' - '.join(map(str, numbers))}",
            f"🏆 Predicted order: {' - '.join(map(str, predicted_order[:5]))}",
            f"🔎 Order engine: {' - '.join(map(str, order_top5[:5])) if order_top5 else 'unavailable'}",
            f"🧠 Engine agreement: {agreement}",
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

    if not (is_v3 and decision == "NO_BET") and (monitor.get("warning") or payload.get("warning")):
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
