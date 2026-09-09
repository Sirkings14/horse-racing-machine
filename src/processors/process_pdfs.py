from pathlib import Path
from datetime import datetime
import hashlib

from src.processors.pdf_reader import read_pdf_file


PROGRAMS_FOLDER = Path("data/raw/programs")
RESULTS_FOLDER = Path("data/raw/results")

PROCESSED_FOLDER = Path("data/processed")


def make_output_name(pdf_path):
    """
    Create a short, unique filename.
    """

    file_hash = hashlib.md5(
        str(pdf_path).encode("utf-8")
    ).hexdigest()[:10]

    return f"{pdf_path.stem}_{file_hash}.txt"


def ensure_directory(path):
    """
    Ensure that a path exists and is a directory.
    """

    if path.exists() and not path.is_dir():
        raise RuntimeError(
            f"Expected a directory but found a file: {path}"
        )

    path.mkdir(
        parents=True,
        exist_ok=True
    )


def process_folder(source_folder, document_type):
    """
    Process every PDF inside a folder.
    """

    output_folder = PROCESSED_FOLDER / document_type

    ensure_directory(
        output_folder
    )

    pdf_files = sorted(
        source_folder.glob("*.pdf")
    )

    print("\n" + "=" * 60)
    print(f"PROCESSING {document_type.upper()}")
    print("=" * 60)

    print(
        f"PDF files found: {len(pdf_files)}"
    )

    processed_count = 0
    failed_count = 0
    skipped_count = 0

    for pdf_file in pdf_files:

        try:

            output_name = make_output_name(
                pdf_file
            )

            output_path = (
                output_folder /
                output_name
            )

            if output_path.exists():

                print(
                    f"Already processed: "
                    f"{pdf_file.name}"
                )

                skipped_count += 1

                continue

            result = read_pdf_file(
                pdf_file
            )

            extracted_text = result["text"]

            if not extracted_text.strip():

                print(
                    f"No readable text found: "
                    f"{pdf_file.name}"
                )

                failed_count += 1

                continue

            header = (
                f"DOCUMENT TYPE: {document_type}\n"
                f"SOURCE FILE: {pdf_file.name}\n"
                f"PROCESSED AT: "
                f"{datetime.utcnow().isoformat()}Z\n"
                f"TEXT LENGTH: "
                f"{len(extracted_text)}\n"
                f"{'=' * 60}\n\n"
            )

            output_path.write_text(
                header + extracted_text,
                encoding="utf-8"
            )

            print(
                f"Processed successfully: "
                f"{pdf_file.name}"
            )

            processed_count += 1

        except Exception as error:

            print(
                f"Processing failed for "
                f"{pdf_file.name}: {error}"
            )

            failed_count += 1

    print(
        f"Processed: {processed_count} | "
        f"Skipped: {skipped_count} | "
        f"Failed: {failed_count}"
    )

    return (
        processed_count,
        failed_count,
        skipped_count
    )


def process_all_pdfs():

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("PDF PROCESSING ENGINE")
    print("=" * 60)

    ensure_directory(
        PROGRAMS_FOLDER
    )

    ensure_directory(
        RESULTS_FOLDER
    )

    ensure_directory(
        PROCESSED_FOLDER
    )

    (
        program_success,
        program_failed,
        program_skipped
    ) = process_folder(
        PROGRAMS_FOLDER,
        "programs"
    )

    (
        result_success,
        result_failed,
        result_skipped
    ) = process_folder(
        RESULTS_FOLDER,
        "results"
    )

    print("\n" + "=" * 60)

    print("PDF PROCESSING COMPLETE")

    print(
        f"Programs processed: "
        f"{program_success}"
    )

    print(
        f"Programs skipped: "
        f"{program_skipped}"
    )

    print(
        f"Program failures: "
        f"{program_failed}"
    )

    print(
        f"Results processed: "
        f"{result_success}"
    )

    print(
        f"Results skipped: "
        f"{result_skipped}"
    )

    print(
        f"Result failures: "
        f"{result_failed}"
    )

    print("=" * 60)


if __name__ == "__main__":
    process_all_pdfs()
