from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"
MEMORY_FILE = BASE_DIR / "data" / "memory" / "race_memory.json"

def main() -> None:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for row in rows: grouped[str(row["race_key"])].append(row)
    races = []
    for key, race_rows in sorted(grouped.items()):
        ordered = sorted(race_rows, key=lambda r:r.get("finish_position") or 999)
        races.append({"race_key":key,"winner":next((r["horse_number"] for r in ordered if r.get("won")==1),None),
            "top3":[r["horse_number"] for r in ordered if r.get("top3")==1],
            "top4":[r["horse_number"] for r in ordered if r.get("top4")==1],
            "top5":[r["horse_number"] for r in ordered if r.get("top5")==1]})
    MEMORY_FILE.parent.mkdir(parents=True,exist_ok=True)
    MEMORY_FILE.write_text(json.dumps({"memory_version":1,"race_count":len(races),"horse_row_count":len(rows),"races":races},indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Remembered races: {len(races)}")

if __name__ == "__main__":
    main()
