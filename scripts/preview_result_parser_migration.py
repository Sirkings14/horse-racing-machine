"""Generate a read-only, roster-checked preview for correcting structured arrivals.

No input JSON is modified. A race is eligible only when every matching structured
copy reparses, all corrected arrival sequences agree, each candidate is a pure
trailing-value trim, and the proposed arrival validates against an available
non-conflicting runner roster. The manifest is for human review, not official
truth approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.learning.result_truth import build_program_runner_index, canonical_key, validate_arrival
from src.parsers.results_parser import parse_result_file

DEFAULT_PROCESSED_DIR = BASE_DIR / "data" / "processed" / "results"
DEFAULT_STRUCTURED_DIR = BASE_DIR / "data" / "structured" / "results"
DEFAULT_OUTPUT = BASE_DIR / "data" / "evaluation" / "result_parser_migration_preview.json"


def _sha256_file(path: Path) -> str:
    """Fingerprint exact input bytes so a later migration can detect stale previews."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _roster_sha256(meta: dict[str, Any] | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    numbers = meta.get("horse_numbers")
    if not isinstance(numbers, (set, list, tuple)):
        return None
    canonical = {
        "horse_numbers": sorted(_int(number) for number in numbers if _int(number) is not None),
        "runners_count": _int(meta.get("runners_count")),
        "source_file": meta.get("source_file"),
        "conflict": bool(meta.get("conflict")),
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result <= 0 or (isinstance(value, float) and result != value):
        return None
    return result


def _arrival(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        number = _int(item)
        if number is None:
            return None
        out.append(number)
    return out


def _races(payload: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("races"), list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for race in payload["races"]:
        if not isinstance(race, dict):
            continue
        number = _int(race.get("race_number"))
        if number is not None:
            out[number] = race
    return out


def _pure_tail_trim(old: list[int] | None, new: list[int] | None) -> bool:
    return bool(
        old is not None and new is not None
        and len(old) > len(new) >= 3
        and old[:len(new)] == new
    )


def preview_migration(
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    structured_dir: Path = DEFAULT_STRUCTURED_DIR,
    program_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a candidate manifest without mutating structured result files."""
    if program_index is None:
        program_index = build_program_runner_index()

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    text_paths = sorted(processed_dir.glob("*.txt")) if processed_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "preview_only",
        "processed_text_files_seen": len(text_paths),
        "structured_files_checked": 0,
        "structured_files_missing_text": 0,
        "parse_errors": 0,
        "result_copies_seen": 0,
        "result_groups_seen": 0,
        "migration_preview_eligible_groups": 0,
        "migration_preview_eligible_copies": 0,
        "blocked_groups": 0,
        "blocked_reason_counts": {},
        "error_samples": errors,
        "eligible_groups": [],
        "policy": {
            "read_only": True,
            "modifies_structured_results": False,
            "modifies_training_dataset": False,
            "modifies_model_bundle": False,
            "live_prediction_or_betting_effect": "none",
            "eligibility_is_not_official_truth_approval": True,
            "apply_requires_a_separate_reviewed_migration": True,
            "each_candidate_records_input_sha256": True,
            "stale_inputs_must_be_repreviewed_before_any_future_apply": True,
            "source_files_are_never_rewritten_by_this_preview": True,
        },
    }

    for text_path in text_paths:
        structured_path = structured_dir / f"{text_path.stem}.json"
        if not structured_path.exists():
            report["structured_files_missing_text"] += 1
            continue
        try:
            structured_sha256 = _sha256_file(structured_path)
            processed_text_sha256 = _sha256_file(text_path)
            previous = json.loads(structured_path.read_text(encoding="utf-8"))
            reparsed = parse_result_file(text_path)
        except Exception as error:
            report["parse_errors"] += 1
            if len(errors) < 20:
                errors.append({"file": text_path.name, "error": type(error).__name__})
            continue

        report["structured_files_checked"] += 1
        old_map = _races(previous)
        new_map = _races(reparsed)
        for number, old_race in old_map.items():
            date_value = previous.get("date") or reparsed.get("date")
            track_value = previous.get("track") or reparsed.get("track")
            key = canonical_key(date_value, track_value, number)
            if not key:
                counts["invalid_race_identity"] += 1
                continue
            old_arrival = _arrival(old_race.get("arrival"))
            new_race = new_map.get(number)
            if new_race is None:
                groups[key].append({
                    "file": structured_path.name,
                    "text_file": text_path.name,
                    "old_arrival": old_arrival,
                    "new_arrival": None,
                    "race_number": number,
                    "race_key": key,
                    "structured_sha256": structured_sha256,
                    "processed_text_sha256": processed_text_sha256,
                    "roster_evidence_sha256": _roster_sha256(program_index.get(key)),
                    "change_type": "source_reparse_missing",
                    "roster_validation": {"accepted_for_learning": False, "reason": "source_reparse_missing"},
                })
                continue

            reparsed_key = canonical_key(
                reparsed.get("date"), reparsed.get("track"), number
            )
            proposed = _arrival(new_race.get("arrival"))
            if reparsed_key != key:
                change_type = "source_identity_mismatch"
            elif proposed is None or old_arrival is None:
                change_type = "invalid_arrival_shape"
            elif proposed == old_arrival:
                change_type = "unchanged"
            elif _pure_tail_trim(old_arrival, proposed):
                change_type = "tail_trim_candidate"
            else:
                change_type = "arrival_sequence_changed"

            validation = validate_arrival(key, proposed or [], program_index)
            groups[key].append({
                "file": structured_path.name,
                "text_file": text_path.name,
                "race_number": number,
                "race_key": key,
                "old_arrival": old_arrival,
                "new_arrival": proposed,
                "structured_sha256": structured_sha256,
                "processed_text_sha256": processed_text_sha256,
                "roster_evidence_sha256": _roster_sha256(program_index.get(key)),
                "change_type": change_type,
                "roster_validation": validation,
            })
            report["result_copies_seen"] += 1

    eligible = []
    for race_key, observations in sorted(groups.items()):
        report["result_groups_seen"] += 1
        proposal_values = {
            tuple(item["new_arrival"]) for item in observations
            if isinstance(item.get("new_arrival"), list)
        }
        changed = any(item.get("change_type") == "tail_trim_candidate" for item in observations)
        proposed_missing = any(item.get("new_arrival") is None for item in observations)
        bad_change = any(item.get("change_type") not in ("unchanged", "tail_trim_candidate") for item in observations)
        copy_disagreement = len(proposal_values) != 1
        invalid_roster = any(
            not (item.get("roster_validation") or {}).get("accepted_for_learning")
            for item in observations
        )

        reasons = []
        if proposed_missing:
            reasons.append("source_reparse_missing")
        if bad_change:
            reasons.extend(sorted({
                str(item.get("change_type"))
                for item in observations
                if item.get("change_type") not in ("unchanged", "tail_trim_candidate")
            }))
        if copy_disagreement:
            reasons.append("copies_disagree_after_reparse")
        if invalid_roster:
            reasons.extend(sorted({
                str((item.get("roster_validation") or {}).get("reason") or "roster_validation_failed")
                for item in observations
                if not (item.get("roster_validation") or {}).get("accepted_for_learning")
            }))
        if not changed:
            continue

        if reasons:
            report["blocked_groups"] += 1
            for reason in set(reasons):
                counts[reason] += 1
            continue

        proposed_arrival = list(next(iter(proposal_values)))
        eligible.append({
            "race_key": race_key,
            "proposed_arrival": proposed_arrival,
            "structured_result_copies": observations,
            "eligible_reason": "all copies agree; pure tail trim; corrected arrival passes available roster validation",
            "status": "eligible_for_review_only",
        })

    report["migration_preview_eligible_groups"] = len(eligible)
    report["migration_preview_eligible_copies"] = sum(
        sum(item.get("change_type") == "tail_trim_candidate" for item in group["structured_result_copies"])
        for group in eligible
    )
    report["blocked_reason_counts"] = dict(sorted(counts.items()))
    report["eligible_groups"] = eligible
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview safe-looking result corrections without applying them.")
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR))
    parser.add_argument("--structured-dir", default=str(DEFAULT_STRUCTURED_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = preview_migration(Path(args.processed_dir), Path(args.structured_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        key: report[key] for key in (
            "processed_text_files_seen", "structured_files_checked", "structured_files_missing_text",
            "parse_errors", "result_copies_seen", "result_groups_seen",
            "migration_preview_eligible_groups", "migration_preview_eligible_copies",
            "blocked_groups", "blocked_reason_counts",
        )
    }
    summary["output"] = str(output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
