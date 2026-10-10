from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.live.registry import mark_result_verified
from src.matching.race_matcher import normalize_track
from src.learning.result_truth import build_program_runner_index, validate_arrival

BASE_DIR = Path(__file__).resolve().parents[2]
PREDICTIONS_DIR = BASE_DIR / "data" / "predictions"
RESULTS_DIR = BASE_DIR / "data" / "structured" / "results"
EVALUATION_DIR = BASE_DIR / "data" / "evaluation"
EVALUATION_FILE = EVALUATION_DIR / "prediction_evaluations.json"
V4_PERFORMANCE_FILE = EVALUATION_DIR / "v4_live_performance.json"

V4_MODES = {"v3_evidence_no_press", "v4_evidence_no_press"}
LEGACY_MODES = {"live_registry_prediction"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_key(value: str) -> str:
    parts = str(value).split("|", 2)
    if len(parts) != 3:
        return str(value)
    try:
        number = int(parts[2])
    except ValueError:
        return str(value)
    return f"{parts[0][:10]}|{normalize_track(parts[1])}|{number}"


def result_records(program_index: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return only unique, non-conflicting result truth matched to an unambiguous roster."""
    audit: dict[str, Any] = {
        "result_races_seen": 0,
        "accepted": 0,
        "rejected": 0,
        "validated_result_documents": 0,
        "duplicate_result_documents": 0,
        "conflicting_result_races": 0,
        "conflicting_result_documents": 0,
        "unidentifiable_result_races": 0,
        "program_roster_conflicts": sum(1 for meta in program_index.values() if meta.get("conflict")),
        "rejection_reasons": {},
        "rejection_reason_counts_are_nonexclusive": True,
    }
    candidates: dict[str, list[dict[str, Any]]] = {}

    def reject(reason: str) -> None:
        audit["rejected"] += 1
        reason_counts = audit["rejection_reasons"]
        for reason_item in str(reason or "unknown_rejection_reason").split(";"):
            normalized = reason_item.strip() or "unknown_rejection_reason"
            reason_counts[normalized] = reason_counts.get(normalized, 0) + 1

    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable result {path.name}: {error}")
            continue
        if not isinstance(payload, dict) or payload.get("document_type") != "result":
            continue
        race_date = str(payload.get("date") or "")[:10]
        track = normalize_track(payload.get("track"))
        for race in payload.get("races") or []:
            audit["result_races_seen"] += 1
            try:
                number = int(race.get("race_number"))
            except (TypeError, ValueError):
                reject("invalid_race_number")
                audit["unidentifiable_result_races"] += 1
                continue
            if not race_date or not track:
                reject("missing_race_date_or_track")
                audit["unidentifiable_result_races"] += 1
                continue

            raw_arrival = race.get("arrival")
            if not isinstance(raw_arrival, list):
                reject("invalid_arrival_format")
                continue
            arrival: list[int] = []
            invalid_arrival = False
            for value in raw_arrival:
                try:
                    if isinstance(value, bool):
                        raise ValueError("boolean is not a horse number")
                    parsed = int(value)
                    if isinstance(value, float) and value != parsed:
                        raise ValueError("fractional arrival number")
                    arrival.append(parsed)
                except (TypeError, ValueError, OverflowError):
                    invalid_arrival = True
                    break
            if invalid_arrival:
                reject("invalid_arrival_values")
                continue

            key = f"{race_date}|{track}|{number}"
            truth = validate_arrival(key, arrival, program_index)
            if not truth["accepted_for_learning"]:
                reject(str(truth.get("reason") or "result_truth_validation_failed"))
                print(f"Skipping untrusted result {key}: {truth['reason']}")
                continue

            candidates.setdefault(key, []).append({
                "source_file": path.name,
                "record": {
                    "race_key": key,
                    "date": race_date,
                    "track": track,
                    "race_number": number,
                    "arrival": arrival,
                    "winner": arrival[0],
                    "second": arrival[1],
                    "third": arrival[2],
                    "truth_validation": truth,
                },
            })

    for key, copies in sorted(candidates.items()):
        audit["validated_result_documents"] += len(copies)
        arrivals = {tuple(item["record"]["arrival"]) for item in copies}
        if len(arrivals) > 1:
            # A result race with multiple distinct, roster-valid arrivals is not
            # safe to learn from. Quarantine the whole race instead of choosing
            # whichever file happens to be processed last.
            audit["conflicting_result_races"] += 1
            audit["conflicting_result_documents"] += len(copies)
            audit["rejected"] += len(copies)
            reasons = audit["rejection_reasons"]
            reasons["conflicting_result_arrivals"] = (
                reasons.get("conflicting_result_arrivals", 0) + len(copies)
            )
            print(f"Quarantining conflicting result records for {key}: {len(arrivals)} different arrivals.")
            continue

        selected = min(copies, key=lambda item: item["source_file"])
        records[key] = selected["record"]
        audit["accepted"] += 1
        audit["duplicate_result_documents"] += max(0, len(copies) - 1)

    return records, audit

def load_existing(program_index: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
    if not EVALUATION_FILE.exists():
        return {}, 0
    try:
        payload = load_json(EVALUATION_FILE)
    except Exception:
        return {}, 0
    if not isinstance(payload, list):
        return {}, 0

    cleaned: dict[str, dict[str, Any]] = {}
    quarantined = 0
    for item in payload:
        if not isinstance(item, dict) or not item.get("race_key"):
            continue
        key = canonical_key(str(item.get("race_key")))
        arrival = []
        for value in ((item.get("result") or {}).get("arrival") or []):
            try:
                arrival.append(int(value))
            except (TypeError, ValueError):
                pass
        truth = validate_arrival(key, arrival, program_index)
        if not truth["accepted_for_learning"]:
            quarantined += 1
            continue
        cleaned[key] = item

    if quarantined:
        print(f"Quarantined {quarantined} previously stored evaluation(s) failing result-truth validation.")
    return cleaned, quarantined


def _engine_metrics(predicted: list[int], actual_top3: list[int], actual_top5: list[int]) -> dict[str, Any]:
    top3 = predicted[:3]
    top5 = predicted[:5]
    winner = actual_top5[0] if actual_top5 else None
    return {
        "winner_hit": bool(predicted) and predicted[0] == winner,
        "winner_in_top3": winner in top3,
        "winner_in_top5": winner in top5,
        "actual_top3_covered_by_top3": len(set(actual_top3) & set(top3)),
        "actual_top3_covered_by_top5": len(set(actual_top3) & set(top5)),
        "actual_top5_covered_by_top5": len(set(actual_top5) & set(top5)),
        "exact_top3_order": top3 == actual_top3,
        "exact_top5_order": top5 == actual_top5,
        "top5_position_hits": sum(
            1 for position, horse in enumerate(top5)
            if position < len(actual_top5) and horse == actual_top5[position]
        ),
    }


def _ranked_numbers(prediction: dict[str, Any]) -> list[int]:
    return [
        int(item["horse_number"])
        for item in (prediction.get("ranked_horses") or [])
        if isinstance(item, dict) and item.get("horse_number") is not None
    ][:5]


def evaluate(prediction: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    actual_top3 = result["arrival"][:3]
    actual_top5 = result["arrival"][:5]
    ranked_top5 = _ranked_numbers(prediction)

    # V4 deliberately clears final_five/recommended_numbers when NO_BET is
    # enforced. Preserve the model's ranked candidates separately so the
    # observation phase can still measure predictive quality without turning
    # them into betting recommendations.
    v4_mode = prediction.get("mode") in V4_MODES
    model_candidates = (
        ranked_top5 if v4_mode else
        [int(x) for x in prediction.get("recommended_numbers") or []]
    )
    predicted_top3 = (
        ranked_top5[:3] if v4_mode else
        [int(x) for x in prediction.get("top3_numbers") or []]
    )
    predicted_order = (
        [int(x) for x in prediction.get("predicted_finish_order") or []]
        if not v4_mode else ranked_top5
    )
    order_top5 = [int(x) for x in prediction.get("order_engine_top5") or []]
    fused_top5 = predicted_order[:5] if predicted_order else predicted_top3[:5]
    predicted_winner = fused_top5[0] if fused_top5 else None

    strength_metrics = _engine_metrics(ranked_top5, actual_top3, actual_top5)
    order_metrics = _engine_metrics(order_top5, actual_top3, actual_top5)
    fused_metrics = _engine_metrics(fused_top5, actual_top3, actual_top5)

    guard = prediction.get("autopilot_guard") or {}
    live_decision = prediction.get("live_decision")
    gate_reasons = guard.get("gate_reasons") or prediction.get("no_bet_reason") or []

    return {
        "race_key": prediction.get("race_key"),
        "prediction_id": prediction.get("prediction_id"),
        "model_version": prediction.get("model_version", "unknown"),
        "mode": prediction.get("mode"),
        "predicted_at": prediction.get("generated_at"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "prediction": {
            "recommended_numbers": [int(x) for x in prediction.get("recommended_numbers") or []],
            "model_candidates": model_candidates,
            "top3_numbers": predicted_top3,
            "ranked_top5": ranked_top5,
            "predicted_finish_order_top5": predicted_order[:5],
            "order_engine_top5": order_top5[:5],
            "confidence": prediction.get("confidence"),
            "model_agreement": prediction.get("model_agreement"),
            "monitoring": prediction.get("monitoring") or {},
            "difficulty": prediction.get("difficulty") or {},
            "live_decision": live_decision,
            "gate_reasons": gate_reasons,
        },
        "metrics": {
            "winner_hit": predicted_winner == result.get("winner"),
            "winner_in_top3": result.get("winner") in predicted_top3,
            "winner_in_top5": result.get("winner") in ranked_top5,
            "order_engine_winner_hit": order_metrics["winner_hit"],
            "strength_engine_winner_hit": strength_metrics["winner_hit"],
            "fused_engine_winner_hit": fused_metrics["winner_hit"],
            "actual_top3_covered_by_predicted_top3": len(set(actual_top3) & set(predicted_top3)),
            "actual_top3_covered_by_predicted_top5": len(set(actual_top3) & set(ranked_top5)),
            "recommended_hit_count": len(set(prediction.get("recommended_numbers") or []) & set(result["arrival"])),
            "model_candidate_hit_count": len(set(model_candidates) & set(result["arrival"])),
            "exact_top3_order": fused_metrics["exact_top3_order"],
            "exact_top5_order": fused_metrics["exact_top5_order"],
            "top5_position_hits": fused_metrics["top5_position_hits"],
            "engine_attribution": {
                "strength": strength_metrics,
                "order": order_metrics,
                "fused": fused_metrics,
            },
        },
        "status": "result_verified",
        "result_validation": result.get("truth_validation") or {
            "accepted_for_learning": True,
            "minimum_positions_required": 3,
            "arrival_positions_available": len(result["arrival"]),
        },
    }


def _build_v4_performance(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        item for item in evaluations
        if isinstance(item, dict) and item.get("mode") in V4_MODES
        and item.get("status") == "result_verified"
    ]
    total = len(rows)
    if not total:
        return {
            "status": "awaiting_verified_v4_results",
            "model": "v4-evidence-no-press",
            "verified_races": 0,
            "betting_clear_races": 0,
            "no_bet_races": 0,
            "predictive_metrics": {},
            "policy": {
                "predictive_validation_is_not_profitability_validation": True,
                "no_bet_remains_default_without_economic_validation": True,
            },
        }

    def avg(key: str) -> float:
        return round(sum(float(item["metrics"].get(key, 0)) for item in rows) / total, 4)

    no_bet = sum(1 for item in rows if (item.get("prediction") or {}).get("live_decision") == "NO_BET")
    return {
        "status": "observation",
        "model": "v4-evidence-no-press",
        "verified_races": total,
        "betting_clear_races": total - no_bet,
        "no_bet_races": no_bet,
        "predictive_metrics": {
            "winner_hit_rate": avg("winner_hit"),
            "winner_in_top3_rate": avg("winner_in_top3"),
            "winner_in_top5_rate": avg("winner_in_top5"),
            "average_actual_top3_covered_by_predicted_top3": avg("actual_top3_covered_by_predicted_top3"),
            "average_actual_top3_covered_by_predicted_top5": avg("actual_top3_covered_by_predicted_top5"),
            "average_model_candidate_hit_count": avg("model_candidate_hit_count"),
        },
        "confidence_breakdown": {
            level: sum(1 for item in rows if (item.get("prediction") or {}).get("confidence") == level)
            for level in ("high", "medium", "low")
        },
        "agreement_breakdown": {
            level: sum(1 for item in rows if (item.get("prediction") or {}).get("model_agreement") == level)
            for level in ("high", "medium", "low")
        },
        "policy": {
            "predictive_validation_is_not_profitability_validation": True,
            "no_bet_remains_default_without_economic_validation": True,
            "observed_market_prices_required_for_economic_claims": True,
        },
    }


def safe_prediction_files() -> list[Path]:
    return sorted(PREDICTIONS_DIR.glob("*.json")) if PREDICTIONS_DIR.exists() else []


def main() -> dict[str, Any]:
    program_index = build_program_runner_index()
    results, truth_audit = result_records(program_index)
    evaluations, quarantined_evaluations = load_existing(program_index)
    processed = 0

    for path in safe_prediction_files():
        try:
            prediction = load_json(path)
        except Exception as error:
            print(f"Skipping unreadable prediction {path.name}: {error}")
            continue
        mode = prediction.get("mode")
        if mode not in (LEGACY_MODES | V4_MODES):
            continue
        original_key = prediction.get("race_key")
        if not original_key:
            continue
        key = canonical_key(str(original_key))
        if key in evaluations:
            continue
        result = results.get(key)
        if not result:
            continue
        evaluations[key] = evaluate(prediction, result)
        mark_result_verified(str(original_key), str(EVALUATION_FILE.relative_to(BASE_DIR)))
        processed += 1

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    truth_audit["stored_evaluations_quarantined"] = quarantined_evaluations
    ordered = [evaluations[key] for key in sorted(evaluations)]
    (EVALUATION_DIR / "result_truth_audit.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                **truth_audit,
                "stored_verified_evaluations_after_quarantine": len(ordered),
                "v4_verified_races": sum(1 for item in ordered if item.get("mode") in V4_MODES),
                "policy": {
                    "unknown_result_numbers_never_train": True,
                    "duplicate_arrival_numbers_never_train": True,
                    "fewer_than_three_positions_never_train": True,
                    "program_roster_is_authoritative": True,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    EVALUATION_FILE.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")
    v4_report = _build_v4_performance(ordered)
    v4_report["generated_at"] = datetime.now(timezone.utc).isoformat()
    V4_PERFORMANCE_FILE.write_text(json.dumps(v4_report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Verified prediction/result pairs added: {processed}")
    print(f"Total verified prediction/result pairs: {len(ordered)}")
    print(f"Verified V4 observation races: {v4_report['verified_races']}")
    print(f"Result truth audit: {truth_audit['accepted']} accepted / {truth_audit['rejected']} rejected.")
    return {"processed": processed, "total": len(ordered), "v4_report": v4_report, "path": str(EVALUATION_FILE)}


if __name__ == "__main__":
    main()
