from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.model.market_evidence import append_snapshot, normalize_snapshot


def load_snapshot_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError("Input must be one snapshot object or a list of snapshot objects.")


def import_snapshot_file(path: Path) -> dict[str, int]:
    snapshots = load_snapshot_file(path)
    accepted = 0
    rejected = 0
    duplicates = 0
    for snapshot in snapshots:
        normalized = normalize_snapshot(snapshot)
        if normalized is None:
            rejected += 1
            continue
        if append_snapshot(normalized):
            accepted += 1
        else:
            duplicates += 1
    return {"input": len(snapshots), "accepted": accepted, "rejected": rejected, "duplicates": duplicates}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import source-attributed, timestamped pre-race market odds into the evidence ledger."
    )
    parser.add_argument("snapshot_file", type=Path, help="JSON file containing one snapshot or a list of snapshots")
    args = parser.parse_args()

    try:
        result = import_snapshot_file(args.snapshot_file)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
        return 2

    print("Market odds evidence import")
    print(f"Input snapshots: {result['input']}")
    print(f"Accepted: {result['accepted']}")
    print(f"Rejected (invalid/missing provenance or not pre-race): {result['rejected']}")
    print(f"Duplicates: {result['duplicates']}")
    if result["accepted"] == 0:
        print("No new market evidence was recorded.")
    return 0 if result["rejected"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
