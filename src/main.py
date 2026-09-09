from src.scraper import run_scraper
from src.processors.process_pdfs import process_all_pdfs


def main():

    print("=" * 60)
    print("STARTING HORSE RACING MACHINE")
    print("=" * 60)

    # STEP 1
    # Download the latest race programs and results
    print("\nSTEP 1: SCRAPING LONAB DATA")

    run_scraper()

    # STEP 2
    # Extract readable text from all downloaded PDFs
    print("\nSTEP 2: PROCESSING RACE PDFs")

    process_all_pdfs()

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE FINISHED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
