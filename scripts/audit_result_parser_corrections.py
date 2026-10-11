"""Read-only audit of arrival changes caused by the corrected result parser.

Compares each processed result text file against its saved structured JSON.
It writes only a separate audit report and never rewrites any saved result,
dataset, or model artifact.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.parsers.results_parser import parse_result_file
from src.learning.result_truth import build_program_runner_index, canonical_key, validate_arrival
DEFAULT_PROCESSED_DIR = BASE_DIR / "data" / "processed" / "results"
DEFAULT_STRUCTURED_DIR = BASE_DIR / "data" / "structured" / "results"
DEFAULT_OUTPUT = BASE_DIR / "data" / "evaluation" / "result_parser_correction_audit.json"
SAMPLE_LIMIT = 200


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number <= 0 or (isinstance(value, float) and number != value):
        return None
    return number


def _arrival(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = []
    for item in value:
        number = _positive_int(item)
        if number is None:
            return []
        numbers.append(number)
    return numbers


def compare_arrivals(legacy: list[int], reparsed: list[int]) -> str:
    """Classify differences without claiming either side is official truth."""
    if legacy == reparsed:
        return "unchanged"
    if len(legacy) > len(reparsed) and reparsed and legacy[:len(reparsed)] == reparsed:
        return "legacy_has_extra_trailing_values"
    if len(reparsed) > len(legacy) and legacy and reparsed[:len(legacy)] == legacy:
        return "reparse_has_more_positions"
    return "arrival_sequence_changed"


_RANK_PREFIX_PATTERN = re.compile(
    r"^\s*(?P<race>\d+)\s*(?:i[eè]me|ère|ere|er|ème|eme|e)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)


def _classify_unparsed_rank_line(rest: str) -> str:
    """Give reviewers a conservative reason; never infer a missing finish."""
    value = str(rest or "").strip()
    if not value:
        return "rank_label_without_arrival_text"
    if re.match(r"^(?:x|np|da|dai|disq|ab|abd|ret|pulled)", value, re.IGNORECASE):
        return "status_marker_before_arrival_number"
    if re.match(r"^(?:[-–—]\s*){1,}", value):
        return "arrival_sequence_missing_or_corrupt"
    if re.match(r"^\d+\s+", value):
        return "single_number_without_hyphen_separator_payout_ambiguous"
    return "unsupported_or_corrupted_rank_line"


def _source_line_evidence(text_path: Path, race_number: int, max_lines: int = 3) -> list[dict[str, Any]]:
    """Return raw ordinal lines for audit review when legacy race is not reparsed."""
    try:
        lines = text_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    evidence: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(lines, start=1):
        match = _RANK_PREFIX_PATTERN.match(raw_line)
        if not match or _positive_int(match.group("race")) != race_number:
            continue
        rest = match.group("rest")
        evidence.append({
            "line_number": line_number,
            "raw_line": raw_line[:500],
            "review_reason": _classify_unparsed_rank_line(rest),
        })
        if len(evidence) >= max_lines:
            break
    return evidence


def _race_map(payload: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("races"), list):
        return {}
    output: dict[int, dict[str, Any]] = {}
    for race in payload["races"]:
        if not isinstance(race, dict):
            continue
        number = _positive_int(race.get("race_number"))
        if number is not None:
            output[number] = race
    return output


def audit_corpus(
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    structured_dir: Path = DEFAULT_STRUCTURED_DIR,
    sample_limit: int = SAMPLE_LIMIT,
    program_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare proposed corrections and validate their runner numbers; no source mutations."""
    if program_index is None:
        program_index = build_program_runner_index()
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "audit_only",
        "processed_directory": str(processed_dir),
        "structured_directory": str(structured_dir),
        "processed_text_files_seen": 0,
        "matching_structured_files": 0,
        "missing_structured_files": 0,
        "unreadable_structured_files": 0,
        "parser_errors": 0,
        "races_compared": 0,
        "unchanged_races": 0,
        "changed_races": 0,
        "legacy_has_extra_trailing_values": 0,
        "reparse_has_more_positions": 0,
        "arrival_sequence_changed": 0,
        "legacy_only_races": 0,
        "reparsed_only_races": 0,
        "change_type_counts": {},
        "candidate_races_checked_against_roster": 0,
        "roster_valid_correction_candidates": 0,
        "roster_rejected_correction_candidates": 0,
        "roster_rejection_reason_counts": {},
        "error_samples": [],
        "changed_race_samples": [],
        "legacy_only_race_samples": [],
        "policy": {
            "read_only": True,
            "rewrites_structured_results": False,
            "rewrites_training_dataset": False,
            "overwrites_model_bundle": False,
            "change_classification_is_not_official_truth_validation": True,
            "historical_reparse_requires_separate_review": True,
        },
    }
    counts: Counter[str] = Counter()
    text_files = sorted(processed_dir.glob("*.txt")) if processed_dir.exists() else []

    for text_path in text_files:
        report["processed_text_files_seen"] += 1
        structured_path = structured_dir / f"{text_path.stem}.json"
        if not structured_path.exists():
            report["missing_structured_files"] += 1
            continue
        try:
            previous = json.loads(structured_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            report["unreadable_structured_files"] += 1
            if len(report["error_samples"]) < 20:
                report["error_samples"].append({"file": structured_path.name, "error": type(error).__name__})
            continue

        report["matching_structured_files"] += 1
        try:
            reparsed = parse_result_file(text_path)
        except Exception as error:
            report["parser_errors"] += 1
            if len(report["error_samples"]) < 20:
                report["error_samples"].append({"file": text_path.name, "error": type(error).__name__})
            continue

        old_map = _race_map(previous)
        new_map = _race_map(reparsed)
        legacy_only = sorted(set(old_map) - set(new_map))
        reparsed_only = sorted(set(new_map) - set(old_map))
        report["legacy_only_races"] += len(legacy_only)
        report["reparsed_only_races"] += len(reparsed_only)
        for number in legacy_only:
            if len(report["legacy_only_race_samples"]) >= sample_limit:
                break
            source_lines = _source_line_evidence(text_path, number)
            line_reasons = sorted({item["review_reason"] for item in source_lines})
            report["legacy_only_race_samples"].append({
                "file": text_path.name,
                "date": previous.get("date") or reparsed.get("date"),
                "track": previous.get("track") or reparsed.get("track"),
                "race_number": number,
                "legacy_arrival": _arrival(old_map[number].get("arrival")),
                "change_type": "legacy_race_not_reparsed",
                "manual_review_required": True,
                "manual_review_reason": (
                    "no_matching_ordinal_source_line_found" if not source_lines
                    else line_reasons[0] if len(line_reasons) == 1
                    else "multiple_source_line_patterns"
                ),
                "source_line_evidence": source_lines,
            })

        for number in sorted(set(old_map) & set(new_map)):
            old_arrival = _arrival(old_map[number].get("arrival"))
            new_arrival = _arrival(new_map[number].get("arrival"))
            report["races_compared"] += 1
            kind = compare_arrivals(old_arrival, new_arrival)
            if kind == "unchanged":
                report["unchanged_races"] += 1
                continue
            report["changed_races"] += 1
            counts[kind] += 1
            date_value = previous.get("date") or reparsed.get("date")
            track_value = previous.get("track") or reparsed.get("track")
            roster_check = {
                "accepted_for_learning": False,
                "reason": "not_a_tail_only_correction_candidate",
            }
            if kind == "legacy_has_extra_trailing_values":
                race_key = canonical_key(date_value, track_value, number)
                roster_check = validate_arrival(race_key or "", new_arrival, program_index)
                report["candidate_races_checked_against_roster"] += 1
                if roster_check.get("accepted_for_learning"):
                    report["roster_valid_correction_candidates"] += 1
                else:
                    report["roster_rejected_correction_candidates"] += 1
                    reason = str(roster_check.get("reason") or "unknown")
                    rejection_counts = report["roster_rejection_reason_counts"]
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            if len(report["changed_race_samples"]) < sample_limit:
                report["changed_race_samples"].append({
                    "file": text_path.name,
                    "date": date_value,
                    "track": track_value,
                    "race_number": number,
                    "legacy_arrival": old_arrival,
                    "reparsed_arrival": new_arrival,
                    "change_type": kind,
                    "roster_validation": roster_check,
                    "migration_candidate": bool(
                        kind == "legacy_has_extra_trailing_values"
                        and roster_check.get("accepted_for_learning")
                    ),
                })

    report["legacy_has_extra_trailing_values"] = counts["legacy_has_extra_trailing_values"]
    report["reparse_has_more_positions"] = counts["reparse_has_more_positions"]
    report["arrival_sequence_changed"] = counts["arrival_sequence_changed"]
    report["change_type_counts"] = dict(sorted(counts.items()))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit stored result changes without rewriting them.")
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR))
    parser.add_argument("--structured-dir", default=str(DEFAULT_STRUCTURED_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report = audit_corpus(Path(args.processed_dir), Path(args.structured_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = (
        "processed_text_files_seen", "matching_structured_files", "missing_structured_files",
        "unreadable_structured_files", "parser_errors", "races_compared", "unchanged_races",
        "changed_races", "legacy_has_extra_trailing_values", "reparse_has_more_positions",
        "arrival_sequence_changed", "legacy_only_races", "reparsed_only_races", "change_type_counts",
        "candidate_races_checked_against_roster", "roster_valid_correction_candidates",
        "roster_rejected_correction_candidates", "roster_rejection_reason_counts",
    )
    summary = {key: report[key] for key in fields}
    summary["output"] = str(output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
