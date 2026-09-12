from pathlib import Path
import json

from src.scraper import run_scraper

from src.processors.process_pdfs import (
    process_all_pdfs,
)

from src.parsers.program_parser import (
    process_all_programs,
)

from src.parsers.results_parser import (
    process_all_results,
)

from src.matching.race_matcher import (
    run_matching,
)

from src.validators.pipeline_validator import (
    validate_pipeline,
)

from src.dataset.build_dataset import (
    main as build_dataset,
)

from src.dataset.dataset_validator import (
    main as validate_dataset,
)

from src.model.train_model import (
    main as train_model,
)

from src.model.backtest import (
    main as run_backtest,
)

from src.model.predict_latest import (
    main as generate_prediction,
)


BASE_DIR = Path(__file__).resolve().parents[1]
REVIEW_FILE = BASE_DIR / "data" / "dataset" / "dataset_review.json"


def print_step(number, title):
    print("\n" + "=" * 60)
    print(f"STEP {number}: {title}")
    print("=" * 60)


def assert_dataset_clean() -> None:
    if not REVIEW_FILE.exists():
        raise RuntimeError(
            f"Dataset review file was not created: {REVIEW_FILE}"
        )

    with REVIEW_FILE.open("r", encoding="utf-8") as handle:
        review = json.load(handle)

    if not isinstance(review, list):
        raise RuntimeError("dataset_review.json must contain a JSON list.")

    if review:
        print("\nDATASET VALIDATION FAILED")
        for item in review:
            print(f"  {item.get('race_key')}")
            for reason in item.get("reasons", []):
                print(f"    - {reason}")
        raise RuntimeError(
            f"Training dataset rejected {len(review)} race(s)."
        )

    print("\nTraining dataset validation passed: 0 rejected races.")


def main():
    print("\n" + "=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    print_step(1, "SCRAPING LONAB DATA")
    run_scraper()

    print_step(2, "PROCESSING RACE PDFs")
    process_all_pdfs()

    print_step(3, "PARSING PROGRAM DATA")
    process_all_programs()

    print_step(4, "PARSING RESULT DATA")
    process_all_results()

    print_step(5, "VALIDATING PIPELINE DATA")
    validation = validate_pipeline(
        programs_path="data/structured/programs",
        results_path="data/structured/results",
    )

    if not validation.get("valid"):
        raise RuntimeError(
            "Pipeline validation failed; matching and modelling were stopped."
        )

    print("Pipeline validation passed.")

    print_step(6, "MATCHING PROGRAMS WITH RESULTS")
    run_matching(
        programs_path="data/structured/programs",
        results_path="data/structured/results",
        output_path="data/matched/matched_races.json",
        review_path="data/matched/match_review.json",
    )

    print_step(7, "BUILDING TRAINING DATASET")
    build_dataset()

    print_step(8, "VALIDATING TRAINING DATASET")
    validate_dataset()
    assert_dataset_clean()

    print_step(9, "TRAINING FINAL TOP-3 MODEL")
    train_model()

    print_step(10, "RUNNING WALK-FORWARD BACKTEST")
    run_backtest()

    print_step(11, "GENERATING LATEST PREDICTION")
    generate_prediction()

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
