"""Fail-closed, read-only preflight for a result-parser migration preview manifest.

Checks the exact source-text, structured-result, and roster hashes recorded in
each eligible group. It never applies corrections or edits the data archive.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.learning.result_truth import build_program_runner_index
from scripts.preview_result_parser_migration import validate_preview_group_snapshot

DEFAULT_MANIFEST = BASE_DIR / "data" / "evaluation" / "result_parser_migration_preview.json"
DEFAULT_OUTPUT = BASE_DIR / "data" / "evaluation" / "result_parser_migration_preflight.json"
DEFAULT_PROCESSED_DIR = BASE_DIR / "data" / "processed" / "results"
DEFAULT_STRUCTURED_DIR = BASE_DIR / "data" / "structured" / "results"


def preflight_manifest(
    manifest: dict[str, Any],
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    structured_dir: Path = DEFAULT_STRUCTURED_DIR,
    program_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if program_index is None:
        program_index = build_program_runner_index()
    groups = manifest.get("eligible_groups")
    if manifest.get("schema_version") != 2 or manifest.get("status") != "preview_only":
        raise ValueError("Unsupported migration preview manifest schema or status.")
    if not isinstance(groups, list):
        raise ValueError("Migration preview manifest has no eligible_groups list.")

    reasons: Counter[str] = Counter()
    failed_groups: list[dict[str, Any]] = []
    passed = 0
    copies_checked = 0
    for group in groups:
        if not isinstance(group, dict):
            reasons["malformed_candidate_group"] += 1
            if len(failed_groups) < 100:
                failed_groups.append({"reason": "malformed_candidate_group"})
            continue
        check = validate_preview_group_snapshot(group, processed_dir, structured_dir, program_index)
        copies_checked += len(check.get("copy_checks") or [])
        if check.get("valid"):
            passed += 1
            continue
        reason = str(check.get("reason") or "unknown_preflight_failure")
        reasons[reason] += 1
        if len(failed_groups) < 100:
            failed_groups.append({
                "race_key": group.get("race_key"),
                "reason": reason,
                "copy_checks": check.get("copy_checks"),
            })

    total = len(groups)
    status = "all_current" if total > 0 and passed == total else (
        "no_candidates" if total == 0 else "stale_or_invalid_candidates_found"
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_manifest_schema_version": manifest.get("schema_version"),
        "candidate_groups_seen": total,
        "candidate_groups_passed": passed,
        "candidate_groups_failed": total - passed,
        "copies_checked": copies_checked,
        "failure_reason_counts": dict(sorted(reasons.items())),
        "failed_group_samples": failed_groups,
        "policy": {
            "read_only": True,
            "applies_corrections": False,
            "edits_structured_results": False,
            "edits_training_dataset": False,
            "updates_model_bundle": False,
            "all_inputs_are_rehashed_and_roster_is_revalidated": True,
            "any_failed_candidate_blocks_automatic_migration": True,
            "status_all_current_is_not_official_truth_approval": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight a parser migration manifest without applying changes.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--processed-dir", default=str(DEFAULT_PROCESSED_DIR))
    parser.add_argument("--structured-dir", default=str(DEFAULT_STRUCTURED_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not load preview manifest: {type(error).__name__}")

    report = preflight_manifest(
        manifest,
        Path(args.processed_dir),
        Path(args.structured_dir),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        key: report[key] for key in (
            "status", "candidate_groups_seen", "candidate_groups_passed",
            "candidate_groups_failed", "copies_checked", "failure_reason_counts",
        )
    }
    summary["output"] = str(output)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report["status"] in {"all_current", "no_candidates"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
