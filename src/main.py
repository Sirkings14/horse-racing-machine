from src.scraper import run_scraper
from src.processors.process_pdfs import (
    process_all_pdfs
)
from src.parsers.race_parser import (
    parse_all_files
)


def main():

    print("\n" + "=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    print("\nSTEP 1: SCRAPING LONAB DATA")

    run_scraper()

    print("\nSTEP 2: PROCESSING RACE PDFs")

    process_all_pdfs()

    print("\nSTEP 3: PARSING STRUCTURED RACE DATA")

    parse_all_files()

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
