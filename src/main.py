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


def print_step(
    number,
    title,
):
    print(
        "\n"
        + "=" * 60
    )

    print(
        f"STEP {number}: {title}"
    )

    print(
        "=" * 60
    )


def main():

    print(
        "\n"
        + "=" * 60
    )

    print(
        "STARTING HORSE RACING MACHINE"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # STEP 1
    # SCRAPING
    # ========================================================

    print_step(
        1,
        "SCRAPING LONAB DATA",
    )

    run_scraper()

    # ========================================================
    # STEP 2
    # PROCESS PDFs
    # ========================================================

    print_step(
        2,
        "PROCESSING RACE PDFs",
    )

    process_all_pdfs()

    # ========================================================
    # STEP 3
    # PARSE PROGRAMS
    # ========================================================

    print_step(
        3,
        "PARSING PROGRAM DATA",
    )

    process_all_programs()

    # ========================================================
    # STEP 4
    # PARSE RESULTS
    # ========================================================

    print_step(
        4,
        "PARSING RESULT DATA",
    )

    process_all_results()

    # ========================================================
    # STEP 5
    # VALIDATE PIPELINE
    # ========================================================

    print_step(
        5,
        "VALIDATING PIPELINE DATA",
    )

    validation = validate_pipeline(

        programs_path=
            "data/structured/programs",

        results_path=
            "data/structured/results",

    )

    # --------------------------------------------------------
    # STOP PIPELINE IF DATA IS INVALID
    # --------------------------------------------------------

    if not validation.get(
        "valid"
    ):

        print(
            "\n"
            + "=" * 60
        )

        print(
            "PIPELINE VALIDATION FAILED"
        )

        print(
            "=" * 60
        )

        print(
            "\nThe matching engine "
            "will NOT run."
        )

        print(
            "\nFix the parser/data problems "
            "shown above and run again."
        )

        return

    print(
        "\nPipeline validation passed."
    )

    # ========================================================
    # STEP 6
    # MATCH PROGRAMS WITH RESULTS
    # ========================================================

    print_step(
        6,
        "MATCHING PROGRAMS WITH RESULTS",
    )

    run_matching(

        programs_path=
            "data/structured/programs",

        results_path=
            "data/structured/results",

        output_path=
            "data/matched/matched_races.json",

        review_path=
            "data/matched/match_review.json",

    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print(
        "\n"
        + "=" * 60
    )

    print(
        "HORSE RACING MACHINE FINISHED SUCCESSFULLY"
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":

    main()
