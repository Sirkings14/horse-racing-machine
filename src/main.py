from pathlib import Path

from src.scraper import LonabScraper
from src.processors.pdf_processor import PDFProcessor
from src.parsers.program_parser import ProgramParser
from src.parsers.result_parser import ResultParser
from src.matching.race_matcher import RaceMatcher
from src.dataset.dataset_builder import DatasetBuilder


def print_header(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def run_machine():
    print_header("STARTING HORSE RACING MACHINE")

    # ============================================================
    # STEP 1: SCRAPING
    # ============================================================

    print_header("STEP 1: SCRAPING LONAB DATA")

    scraper = LonabScraper()
    scraper.run()

    # ============================================================
    # STEP 2: PDF PROCESSING
    # ============================================================

    print_header("STEP 2: PROCESSING RACE PDFs")

    processor = PDFProcessor()

    program_summary = processor.process_programs()
    result_summary = processor.process_results()

    print_header("PDF PROCESSING COMPLETE")

    print(f"Programs processed: {program_summary.get('processed', 0)}")
    print(f"Programs skipped: {program_summary.get('skipped', 0)}")
    print(f"Program failures: {program_summary.get('failed', 0)}")

    print("-" * 60)

    print(f"Results processed: {result_summary.get('processed', 0)}")
    print(f"Results skipped: {result_summary.get('skipped', 0)}")
    print(f"Result failures: {result_summary.get('failed', 0)}")

    # ============================================================
    # STEP 3: PARSE PROGRAM DATA
    # ============================================================

    print_header("STEP 3: PARSING PROGRAM DATA")

    program_parser = ProgramParser()
    programs = program_parser.parse_all()

    print(f"\nPrograms parsed: {len(programs)}")

    # ============================================================
    # STEP 4: PARSE RESULT DATA
    # ============================================================

    print_header("STEP 4: PARSING RESULT DATA")

    result_parser = ResultParser()
    results = result_parser.parse_all()

    print(f"\nResults parsed: {len(results)}")

    # ============================================================
    # STEP 5: REMOVE DUPLICATES
    # ============================================================

    print_header("STEP 5: DEDUPLICATING RACE DATA")

    unique_programs = {}
    unique_results = {}

    for program in programs:
        key = (
            program.get("date"),
            program.get("track"),
            program.get("race_number")
        )

        # Ignore incomplete records
        if not key[0] or not key[2]:
            continue

        unique_programs[key] = program

    for result in results:
        key = (
            result.get("date"),
            result.get("track"),
            result.get("race_number")
        )

        # Ignore incomplete records
        if not key[0] or not key[2]:
            continue

        unique_results[key] = result

    programs = list(unique_programs.values())
    results = list(unique_results.values())

    print(f"Unique programs: {len(programs)}")
    print(f"Unique results: {len(results)}")

    # ============================================================
    # STEP 6: MATCH PROGRAMS WITH RESULTS
    # ============================================================

    print_header("STEP 6: MATCHING PROGRAMS WITH RESULTS")

    matcher = RaceMatcher()

    matched_races, unmatched_programs = matcher.match(
        programs,
        results
    )

    print("\n" + "=" * 60)
    print("RACE MATCHING COMPLETE")
    print("=" * 60)

    print(f"Matched races: {len(matched_races)}")
    print(f"Unmatched programs: {len(unmatched_programs)}")

    # ============================================================
    # STOP IF NO TRAINING DATA
    # ============================================================

    if not matched_races:
        print("\nNo matched races available.")
        print("Dataset building skipped.")
        return

    # ============================================================
    # STEP 7: BUILD TRAINING DATASET
    # ============================================================

    print_header("STEP 7: BUILDING TRAINING DATASET")

    dataset_builder = DatasetBuilder()

    dataset = dataset_builder.build(matched_races)

    print("\n" + "=" * 60)
    print("DATASET BUILD COMPLETE")
    print("=" * 60)

    print(f"Training rows created: {len(dataset)}")

    # ============================================================
    # FINAL STATUS
    # ============================================================

    print_header("HORSE RACING MACHINE FINISHED SUCCESSFULLY")

    print("Pipeline summary:")
    print(f"Programs: {len(programs)}")
    print(f"Results: {len(results)}")
    print(f"Matched races: {len(matched_races)}")
    print(f"Training examples: {len(dataset)}")


if __name__ == "__main__":
    run_machine()
