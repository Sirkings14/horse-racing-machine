from pathlib import Path
from datetime import datetime, timezone
import hashlib

from src.processors.pdf_reader import read_pdf_file


# ============================================================
# FOLDER CONFIGURATION
# ============================================================

PROGRAMS_FOLDER = Path("data/raw/programs")
RESULTS_FOLDER = Path("data/raw/results")
PROCESSED_FOLDER = Path("data/processed")


# ============================================================
# DIRECTORY SAFETY
# ============================================================

def ensure_directory(path):
    """
    Ensure that the given path exists as a directory.

    Raises an error if something exists at the path
    but it is a file instead of a directory.
    """

    path = Path(path)

    if path.exists():

        if not path.is_dir():

            raise RuntimeError(
                f"Expected directory but found file: {path}"
            )

        return

    path.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# OUTPUT FILENAME
# ============================================================

def make_output_name(pdf_path):
    """
    Create a short and deterministic output filename.

    The hash prevents filename conflicts while keeping
    the generated filename short.
    """

    pdf_path = Path(pdf_path)

    file_hash = hashlib.md5(
        str(pdf_path).encode("utf-8")
    ).hexdigest()[:10]

    return (
        f"{pdf_path.stem}_"
        f"{file_hash}.txt"
    )


# ============================================================
# PROCESS ONE FOLDER
# ============================================================

def process_folder(source_folder, document_type):
    """
    Process every PDF inside a source folder.

    Parameters:
        source_folder: Folder containing PDF files.
        document_type: 'programs' or 'results'.

    Returns:
        processed_count,
        failed_count,
        skipped_count
    """

    source_folder = Path(source_folder)

    output_folder = (
        PROCESSED_FOLDER /
        document_type
    )

    # Make sure both folders exist correctly
    ensure_directory(source_folder)
    ensure_directory(PROCESSED_FOLDER)
    ensure_directory(output_folder)

    pdf_files = sorted(
        source_folder.glob("*.pdf")
    )

    print("\n" + "=" * 60)
    print(
        f"PROCESSING {document_type.upper()}"
    )
    print("=" * 60)

    print(
        f"PDF files found: "
        f"{len(pdf_files)}"
    )

    processed_count = 0
    failed_count = 0
    skipped_count = 0

    # --------------------------------------------------------
    # PROCESS EVERY PDF
    # --------------------------------------------------------

    for pdf_file in pdf_files:

        try:

            output_name = make_output_name(
                pdf_file
            )

            output_path = (
                output_folder /
                output_name
            )

            # Do not process the same PDF twice
            if output_path.exists():

                print(
                    f"Already processed: "
                    f"{pdf_file.name}"
                )

                skipped_count += 1

                continue

            # Read PDF
            result = read_pdf_file(
                pdf_file
            )

            extracted_text = (
                result.get("text", "")
            )

            # Check that useful text exists
            if not extracted_text.strip():

                print(
                    f"No readable text found: "
                    f"{pdf_file.name}"
                )

                failed_count += 1

                continue

            # Metadata header
            processed_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            header = (
                f"DOCUMENT TYPE: "
                f"{document_type}\n"

                f"SOURCE FILE: "
                f"{pdf_file.name}\n"

                f"PROCESSED AT: "
                f"{processed_at}\n"

                f"TEXT LENGTH: "
                f"{len(extracted_text)}\n"

                f"{'=' * 60}\n\n"
            )

            # Save extracted text
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
                f"{pdf_file.name}"
            )

            print(
                f"Reason: {error}"
            )

            failed_count += 1

    # --------------------------------------------------------
    # FOLDER SUMMARY
    # --------------------------------------------------------

    print("\nFolder summary:")

    print(
        f"Processed: "
        f"{processed_count}"
    )

    print(
        f"Skipped: "
        f"{skipped_count}"
    )

    print(
        f"Failed: "
        f"{failed_count}"
    )

    return (
        processed_count,
        failed_count,
        skipped_count
    )


# ============================================================
# PROCESS ALL PROGRAMS AND RESULTS
# ============================================================

def process_all_pdfs():
    """
    Main PDF processing engine.

    Processes:
        - Race program PDFs
        - Race result PDFs
    """

    print("\n" + "=" * 60)
    print("HORSE RACING MACHINE")
    print("PDF PROCESSING ENGINE")
    print("=" * 60)

    # Ensure base directories exist
    ensure_directory(
        PROGRAMS_FOLDER
    )

    ensure_directory(
        RESULTS_FOLDER
    )

    ensure_directory(
        PROCESSED_FOLDER
    )

    # --------------------------------------------------------
    # PROCESS PROGRAMS
    # --------------------------------------------------------

    (
        program_success,
        program_failed,
        program_skipped
    ) = process_folder(
        PROGRAMS_FOLDER,
        "programs"
    )

    # --------------------------------------------------------
    # PROCESS RESULTS
    # --------------------------------------------------------

    (
        result_success,
        result_failed,
        result_skipped
    ) = process_folder(
        RESULTS_FOLDER,
        "results"
    )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("PDF PROCESSING COMPLETE")
    print("=" * 60)

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

    print("-" * 60)

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


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    process_all_pdfs()
