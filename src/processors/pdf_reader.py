from pathlib import Path
from pypdf import PdfReader


def extract_pdf_text(pdf_path):
    """
    Extract text from a PDF file.

    Returns:
        str: Extracted text from all readable pages.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    reader = PdfReader(str(pdf_path))

    pages_text = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text()

            if text:
                pages_text.append(
                    f"\n\n===== PAGE {page_number} =====\n\n{text}"
                )

        except Exception as error:
            print(
                f"Warning: Could not read page "
                f"{page_number} in {pdf_path.name}: {error}"
            )

    return "".join(pages_text)


def read_pdf_file(pdf_path):
    """
    Read one PDF and return metadata plus extracted text.
    """

    pdf_path = Path(pdf_path)

    print(f"Reading PDF: {pdf_path}")

    text = extract_pdf_text(pdf_path)

    return {
        "file_name": pdf_path.name,
        "file_path": str(pdf_path),
        "text": text,
        "text_length": len(text)
    }
