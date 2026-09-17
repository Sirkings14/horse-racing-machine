from __future__ import annotations

import json
from datetime import date, datetime, timezone
import re
from pathlib import Path

from src.live.registry import eligible_races, mark_predicted, LIVE_DIR
from src.model.logistic_model import LogisticModel
from src.model.order_model import OrderModel, fit_order_model
from src.model.race_monitor import build_race_monitor

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MODEL_DIR = BASE_DIR / "data" / "model"
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
OUTPUT_FILE = MODEL_DIR / "latest_prediction.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def race_metadata(program):
    race = program.get("race") or {}
    return {
        "date": program.get("date") or race.get("date"),
        "track": race.get("track") or program.get("track"),
        "race_number": race.get("race_number") if race.get("race_number") is not None else program.get("race_number"),
        "race_name": race.get("race_name") or program.get("race_name"),
        "race_type": race.get("race_type") or program.get("race_type"),
        "distance": race.get("distance") or program.get("distance"),
        "runners_count": race.get("runners_count") or program.get("runners_count"),
    }


def race_key(program):
    meta = race_metadata(program)
    race_date, track, number = meta["date"], meta["track"], meta["race_number"]
    if not race_date or not track or number is None:
        return None
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    return f"{str(race_date).strip()}|{str(track).strip().upper()}|{number}"


def program_to_rows(program):
    meta = race_metadata(program)
    rankings = program.get("rankings") or {}
    positions = {}
    for name in ("favorites", "form", "class", "progress", "regularity"):
        positions[name] = {}
        for i, value in enumerate(rankings.get(name) or [], 1):
            try:
                positions[name][int(value)] = i
            except (TypeError, ValueError):
                pass

    rows = []
    for horse in program.get("horses") or []:
        try:
            number = int(horse.get("number"))
        except (TypeError, ValueError):
            continue
        if number <= 0:
            continue
        ranks = {f"{name}_rank": positions[name].get(number) for name in positions}
        rank_values = [value for value in ranks.values() if value is not None]
        rows.append({
            "race_key": race_key(program),
            "date": meta["date"], "track": meta["track"], "race_number": meta["race_number"],
            "race_name": meta["race_name"], "race_type": meta["race_type"], "distance": meta["distance"],
            "runners_count": meta["runners_count"], "horse_number": number, "horse_name": horse.get("horse"),
            "horse_description": horse.get("description"), **ranks,
            "ranking_average": (sum(rank_values) / len(rank_values) if rank_values else None),
            "ranking_presence": len(rank_values),
        })
    return rows


def normalize_race_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def today_utc():
    return datetime.now(timezone.utc).date()


def write_prediction(result):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    OUTPUT_FILE.write_text(serialized, encoding="utf-8")
    key = result.get("race_key")
    if key:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(key))
        (PREDICTIONS_DIR / f"{safe_name}.json").write_text(serialized, encoding="utf-8")


def no_prediction(reason: str, **extra):
    result = {
        "prediction_id": None, "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": None, "mode": "prediction_unavailable", "reason": reason,
        "recommended_numbers": [], "adaptive_top_count": 0, "ranked_horses": [], **extra,
    }
    write_prediction(result)
    print(f"Prediction unavailable: {reason}")
    return result


def resolve_model_version() -> tuple[str, str]:
    model_registry_path = MODEL_DIR / "model_registry.json"
    try:
        registry = load_json(model_registry_path)
        version = registry.get("champion_version")
        if version:
            return str(version), "registered_champion"
    except Exception:
        pass
    return "legacy-production", "legacy_unregistered_models"


def load_order_model(rows):
    path = MODEL_DIR / "order_model.json"
    if path.exists():
        try:
            return OrderModel.from_dict(load_json(path)), "production_order_model"
        except Exception as error:
            print(f"Production order model unavailable; rebuilding from verified data: {error}")
    try:
        return fit_order_model(rows), "runtime_verified_data_order_model"
    except Exception as error:
        print(f"Order engine unavailable: {error}")
        return None, "order_engine_unavailable"


def main():
    try:
        training_rows = load_json(DATASET_FILE)
        if not isinstance(training_rows, list) or not training_rows:
            raise ValueError("clean training dataset is empty")
    except Exception as error:
        return no_prediction(f"training_dataset_unavailable: {error}")

    models = {}
    for depth in (3, 4, 5):
        model_path = MODEL_DIR / f"top{depth}_model.json"
        try:
            models[depth] = LogisticModel.from_dict(load_json(model_path))
        except Exception as error:
            return no_prediction(f"model_unavailable_top{depth}: {error}")

    today = today_utc()
    races = eligible_races(today.isoformat())
    if not races:
        return no_prediction("no_validated_current_or_future_race", today=today.isoformat(), live_manifest=str(LIVE_DIR / "live_manifest.json"))

    selected_entry = races[0]
    structured_path = LIVE_DIR / str(selected_entry["structured_file"])
    try:
        program = load_json(structured_path)
    except Exception as error:
        return no_prediction(f"live_program_unreadable: {error}", race_key=selected_entry.get("race_key"))

    meta = race_metadata(program)
    actual_date = normalize_race_date(meta["date"])
    rows = program_to_rows(program)
    key = race_key(program)

    if actual_date is None or actual_date < today:
        return no_prediction("live_program_is_stale", race_key=key, today=today.isoformat())
    if not key or not rows:
        return no_prediction("live_program_missing_usable_race_data", race_key=key)

    probabilities = {depth: models[depth].predict_proba(rows) for depth in (3, 4, 5)}
    ranked = []
    for index, row in enumerate(rows):
        p3, p4, p5 = (float(probabilities[depth][index]) for depth in (3, 4, 5))
        score = 0.5 * p3 + 0.3 * p4 + 0.2 * p5
        ranked.append({
            "horse_number": int(row["horse_number"]), "horse_name": row.get("horse_name"),
            "probability_top3": round(p3, 6), "probability_top4": round(p4, 6),
            "probability_top5": round(p5, 6), "ensemble_score": round(score, 6),
        })
    ranked.sort(key=lambda item: (-item["ensemble_score"], item["horse_number"]))
    for index, item in enumerate(ranked, 1):
        item["predicted_rank"] = index

    adaptive = 5
    if len(ranked) >= 5:
        if ranked[2]["probability_top3"] - ranked[3]["probability_top3"] >= 0.12:
            adaptive = 3
        elif ranked[3]["probability_top4"] - ranked[4]["probability_top4"] >= 0.10:
            adaptive = 4

    order_model, order_status = load_order_model(training_rows)
    order_ranking = order_model.predict_order(rows) if order_model else []
    order_map = {item["horse_number"]: item for item in order_ranking}

    # Rank fusion: strength ensemble remains important, while the independent
    # order engine contributes a separate view of the finishing sequence.
    for item in ranked:
        order_item = order_map.get(item["horse_number"])
        order_rank = order_item["predicted_finish_position"] if order_item else len(ranked) + 1
        item["order_rank"] = order_rank
        item["order_win_probability"] = order_item["order_win_probability"] if order_item else None
        item["final_order_score"] = round(
            0.6 * (1.0 / item["predicted_rank"]) + 0.4 * (1.0 / order_rank), 6
        )

    final_order = sorted(ranked, key=lambda item: (-item["final_order_score"], item["horse_number"]))
    for index, item in enumerate(final_order, 1):
        item["final_predicted_position"] = index

    model_version, model_status = resolve_model_version()
    monitoring = build_race_monitor(ranked, order_ranking)

    result = {
        "prediction_id": f"{key}|{datetime.now(timezone.utc).isoformat()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": model_version,
        "model_status": model_status,
        "order_engine_status": order_status,
        "mode": "live_registry_prediction",
        "today": today.isoformat(),
        "source_program": selected_entry.get("source_file"), "source_url": selected_entry.get("source_url"),
        "race_key": key, "race": meta,
        "recommended_numbers": [item["horse_number"] for item in final_order[:adaptive]],
        "adaptive_top_count": adaptive,
        "top3_numbers": [item["horse_number"] for item in final_order[:3]],
        "predicted_finish_order": [item["horse_number"] for item in final_order],
        "order_engine_top5": [item["horse_number"] for item in order_ranking[:5]],
        "winner_engine_candidate": ranked[0]["horse_number"],
        "order_engine_winner_candidate": order_ranking[0]["horse_number"] if order_ranking else None,
        "monitoring": monitoring,
        "ranked_horses": final_order,
        "live_manifest": str(LIVE_DIR / "live_manifest.json"),
    }

    write_prediction(result)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(key))
    mark_predicted(key, str((PREDICTIONS_DIR / f"{safe_name}.json").relative_to(BASE_DIR)))

    print(f"Live race: {result['race_key']}")
    print(f"Model: {model_version} ({model_status})")
    print(f"Order engine: {order_status}")
    print(f"Winner candidates: strength={result['winner_engine_candidate']} order={result['order_engine_winner_candidate']}")
    print(f"Predicted finish order (Top 5): {result['predicted_finish_order'][:5]}")
    print(f"Monitoring agreement: {monitoring['agreement']}")
    print(f"Adaptive recommendation ({adaptive}): {result['recommended_numbers']}")
    return result


if __name__ == "__main__":
    main()
