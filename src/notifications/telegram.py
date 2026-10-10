from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parents[2]
V3_PREDICTION_FILE = BASE_DIR / "data" / "model" / "latest_v3_prediction.json"
LEDGER_FILE = BASE_DIR / "data" / "notifications" / "telegram_delivery_ledger.json"
MAX_LEDGER_ENTRIES = 500


def _load_prediction() -> dict | None:
    """Load only the evidence prediction; never fall back to legacy output."""
    if not V3_PREDICTION_FILE.exists():
        print("Telegram skipped: V4 evidence prediction artifact does not exist.")
        return None
    try:
        payload = json.loads(V3_PREDICTION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Telegram skipped: unreadable V4 prediction: {error}")
        return None
    return payload if isinstance(payload, dict) else None


def _load_delivery_ledger() -> dict[str, Any]:
    try:
        payload = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "notifications": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("notifications"), dict):
        return {"schema_version": 1, "notifications": {}}
    return payload


def _write_delivery_ledger(ledger: dict[str, Any]) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEDGER_FILE.with_suffix(LEDGER_FILE.suffix + ".tmp")
    temporary.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(LEDGER_FILE)


def _semantic_signature(
    candidates: list[Any],
    decision: str,
    gate_reasons: list[Any],
) -> dict[str, Any]:
    normalized_candidates: list[int | str] = []
    for value in candidates:
        try:
            normalized_candidates.append(int(value))
        except (TypeError, ValueError):
            normalized_candidates.append(str(value))
    return {
        "decision": str(decision),
        "candidates_in_order": normalized_candidates,
        "gate_reasons": sorted({str(reason) for reason in gate_reasons if str(reason).strip()}),
    }


def _same_notification_already_sent(race_key: str, signature: dict[str, Any]) -> bool:
    entries = _load_delivery_ledger().get("notifications") or {}
    previous = entries.get(race_key)
    return isinstance(previous, dict) and previous.get("signature") == signature


def _record_successful_delivery(
    race_key: str,
    signature: dict[str, Any],
    prediction: dict[str, Any],
    api_result: dict[str, Any],
) -> None:
    ledger = _load_delivery_ledger()
    entries = ledger.get("notifications")
    if not isinstance(entries, dict):
        entries = {}

    result = api_result.get("result") if isinstance(api_result.get("result"), dict) else {}
    entries[race_key] = {
        "signature": signature,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "prediction_id": prediction.get("prediction_id"),
        "model_version": prediction.get("model_version", "unknown"),
        "telegram_message_id": result.get("message_id"),
    }
    if len(entries) > MAX_LEDGER_ENTRIES:
        newest = sorted(
            entries.items(),
            key=lambda item: str((item[1] or {}).get("sent_at", "")),
            reverse=True,
        )[:MAX_LEDGER_ENTRIES]
        entries = dict(newest)

    ledger["schema_version"] = 1
    ledger["notifications"] = entries
    _write_delivery_ledger(ledger)


def send_latest_prediction() -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram skipped: secrets are not configured.")
        return False

    payload = _load_prediction()
    if payload is None:
        return False

    if payload.get("mode") not in {"v3_evidence_no_press", "v4_evidence_no_press", "v5_market_opportunity_layer"}:
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

    race_key = str(payload.get("race_key") or "").strip()
    if not race_key:
        print("Telegram skipped: prediction is missing its canonical race key.")
        return False

    ranked = payload.get("ranked_horses") or []
    candidates = [
        item.get("horse_number")
        for item in ranked[:5]
        if isinstance(item, dict) and item.get("horse_number") is not None
    ]
    if not candidates:
        candidates = payload.get("recommended_numbers") or []
    if not candidates:
        print("Telegram skipped: prediction contains no ranked candidates.")
        return False

    guard = payload.get("autopilot_guard") or {}
    decision = payload.get("live_decision")
    if not decision:
        decision = "NO_BET" if guard.get("decision") == "PASS" else "PLAY_CANDIDATE"
    gate_reasons = []
    if decision == "NO_BET":
        gate_reasons = guard.get("gate_reasons") or payload.get("no_bet_reason") or [
            "autopilot guard blocked live play"
        ]

    signature = _semantic_signature(candidates, decision, gate_reasons)
    if _same_notification_already_sent(race_key, signature):
        print(f"Telegram skipped: unchanged prediction already sent for {race_key}.")
        return False

    monitor = payload.get("monitoring") or {}
    agreement = monitor.get("agreement") or payload.get("model_agreement", "unknown")
    predicted_order = candidates
    adaptive_depth = len(candidates)
    model_label = payload.get("model_version", "unknown")

    if decision == "NO_BET":
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
            *[f"• {reason}" for reason in gate_reasons],
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

    strategy = payload.get("race_strategy") or {}
    discipline = strategy.get("discipline_label") or race.get("race_type") or "unclassified"
    lines.insert(6, f"Discipline: {discipline} | Data: {strategy.get('evidence_status', 'not assessed')}")
    form_diagnostics = strategy.get("form_diagnostics") or {}
    form_total = int(form_diagnostics.get("runner_count") or 0)
    form_covered = int(form_diagnostics.get("runners_with_numeric_form") or 0)
    if form_total:
        lines.insert(7, f"Recent form parsed: {form_covered}/{form_total} runners (diagnostic only; not in model score)")
    gaps = strategy.get("critical_data_gaps") or []
    if gaps:
        gap_text = ", ".join(
            f"{item.get('field')} {float(item.get('coverage', 0.0)):.0%}"
            for item in gaps[:3]
        )
        lines.insert(8 if form_total else 7, f"Evidence gaps: {gap_text}")

    for horse in ranked[:5]:
        if not isinstance(horse, dict):
            continue
        try:
            probability = float(horse.get("probability_top3", 0))
        except (TypeError, ValueError):
            probability = 0.0
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
    try:
        api_result = response.json()
    except ValueError as error:
        raise RuntimeError("Telegram API returned an unreadable response; delivery was not recorded.") from error
    if not isinstance(api_result, dict) or api_result.get("ok") is not True:
        description = api_result.get("description") if isinstance(api_result, dict) else "invalid API response"
        raise RuntimeError(f"Telegram API did not confirm delivery: {description}")

    # Persist only after Telegram explicitly confirms delivery. Repeated scheduled
    # runs do not spam identical race predictions, while changed candidates or a
    # changed NO_BET decision still produce a new notification.
    _record_successful_delivery(race_key, signature, payload, api_result)
    print("Prediction sent to Telegram and delivery recorded.")
    return True


if __name__ == "__main__":
    send_latest_prediction()
