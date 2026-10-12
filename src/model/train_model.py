from __future__ import annotations

import json
from pathlib import Path

from src.model.logistic_model import fit_top3_model, known_binary_targets
from src.model.order_model import fit_order_model
from src.model.model_registry import CHALLENGER_DIR, new_candidate_version, record_candidate

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_FILE = BASE_DIR / "data" / "dataset" / "training_dataset_clean.json"


def _insufficient_training_target_reason(rows: list[dict]) -> str | None:
    """Require observed positive and negative labels for every challenger target."""
    for depth in (3, 4, 5):
        target_field = f"top{depth}"
        indices, labels = known_binary_targets(rows, target_field)
        positives = sum(labels)
        negatives = len(labels) - positives
        if not indices:
            return f"{target_field} has no known binary labels"
        if positives == 0 or negatives == 0:
            return (
                f"{target_field} has only one observed class "
                f"(known={len(labels)}, positives={positives}, negatives={negatives})"
            )
    return None


def main() -> str | None:
    rows = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        print("Challenger training skipped safely: the clean training dataset is empty or invalid.")
        print("The currently approved production model is unchanged.")
        return None

    issue = _insufficient_training_target_reason(rows)
    if issue:
        # A one-class classifier would be invalid. Skip the entire challenger
        # before creating any candidate files or changing the model registry.
        print(f"Challenger training skipped safely: {issue}.")
        print("No challenger was registered; the currently approved production model is unchanged.")
        return None

    version = new_candidate_version()
    candidate_dir = CHALLENGER_DIR / version
    candidate_dir.mkdir(parents=True, exist_ok=False)

    for depth in (3, 4, 5):
        model = fit_top3_model(rows, target_field=f"top{depth}")
        path = candidate_dir / f"top{depth}_model.json"
        path.write_text(
            json.dumps(model.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Saved challenger Top-{depth} model: {path}")

    order_model = fit_order_model(rows)
    order_path = candidate_dir / "order_model.json"
    order_path.write_text(
        json.dumps(order_model.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Saved challenger finishing-order model: {order_path}")

    record_candidate(
        version,
        {
            "training_races": len({row.get('race_key') for row in rows if row.get('race_key')}),
            "models": ["top3", "top4", "top5", "finishing_order"],
        },
    )
    print(f"Challenger version ready: {version}")
    return version


if __name__ == "__main__":
    main()
