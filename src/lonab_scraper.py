import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.config import (
    LONAB_BASE_URL,
    RAW_PROGRAMS_DIR,
    RAW_RESULTS_DIR,
    REQUEST_TIMEOUT,
    HEADERS,
)


# ============================================================
# OFFICIAL LONAB PAGES
# ============================================================

PROGRAMS_URL = (
    f"{LONAB_BASE_URL}/programme-pmub"
)

RESULTS_URL = (
    f"{LONAB_BASE_URL}/resultats-gains-ecd"
)


class LonabScraper:

    def __init__(self):

        self.session = requests.Session()

        self.session.headers.update(
            HEADERS
        )

        Path(
            RAW_PROGRAMS_DIR
        ).mkdir(
            parents=True,
            exist_ok=True
        )

        Path(
            RAW_RESULTS_DIR
        ).mkdir(
            parents=True,
            exist_ok=True
        )


    # ========================================================
    # HTTP
    # ========================================================

    def fetch_page(self, url):

        response = self.session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        return response.text


    # ========================================================
    # TEXT CLEANING
    # ========================================================

    def clean_text(self, text):

        if not text:
            return ""

        return re.sub(
            r"\s+",
            " ",
            text
        ).strip()


    # ========================================================
    # CLASSIFICATION
    # ========================================================

    def classify_document(self, title):

        title = title.lower()

        if (
            "journal hippique pmu" in title
            or "programme pmu" in title
        ):

            return "program"

        if (
            "récapitulatif des arrivées" in title
            or "recapitulatif des arrivees" in title
            or "résultats pmu" in title
            or "resultats pmu" in title
            or "résultats/gains" in title
        ):

            return "result"

        return "unknown"


    # ========================================================
    # DATE EXTRACTION
    # ========================================================

    def extract_date(self, title):

        patterns = [

            r"\d{2}[/-]\d{2}[/-]\d{4}",

            (
                r"\d{1,2}\s+"
                r"(janvier|février|fevrier|mars|avril|mai|"
                r"juin|juillet|août|aout|septembre|"
                r"octobre|novembre|décembre|decembre)"
                r"\s+\d{4}"
            )

        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                title.lower()
            )

            if match:

                return match.group(0)

        return None


    # ========================================================
    # DOCUMENT DISCOVERY
    # ========================================================

    def discover_documents(
        self,
        page_url
    ):

        print(
            f"Checking: {page_url}"
        )

        html = self.fetch_page(
            page_url
        )

        soup = BeautifulSoup(
            html,
            "lxml"
        )

        documents = []

        seen = set()

        for link in soup.find_all(
            "a",
            href=True
        ):

            href = link.get(
                "href"
            )

            text = self.clean_text(
                link.get_text(
                    " ",
                    strip=True
                )
            )

            absolute_url = urljoin(
                page_url,
                href
            )

            parent_text = ""

            if link.parent:

                parent_text = self.clean_text(
                    link.parent.get_text(
                        " ",
                        strip=True
                    )
                )

            combined_text = (
                f"{text} {parent_text}"
            ).strip()

            document_type = (
                self.classify_document(
                    combined_text
                )
            )

            is_pdf = (
                ".pdf" in
                absolute_url.lower()
            )

            if (
                document_type == "unknown"
                and not is_pdf
            ):

                continue

            if (
                absolute_url in seen
            ):

                continue

            seen.add(
                absolute_url
            )

            documents.append(
                {
                    "title": combined_text,
                    "url": absolute_url,
                    "type": document_type,
                    "date": (
                        self.extract_date(
                            combined_text
                        )
                    ),
                    "is_pdf": is_pdf,
                }
            )

        return documents


    # ========================================================
    # PROGRAM DISCOVERY
    # ========================================================

    def get_program_documents(self):

        documents = (
            self.discover_documents(
                PROGRAMS_URL
            )
        )

        programs = []

        for document in documents:

            if (
                document["type"]
                == "program"
            ):

                programs.append(
                    document
                )

        return programs


    # ========================================================
    # RESULT DISCOVERY
    # ========================================================

    def get_result_documents(self):

        documents = (
            self.discover_documents(
                RESULTS_URL
            )
        )

        results = []

        for document in documents:

            if (
                document["type"]
                == "result"
            ):

                results.append(
                    document
                )

        return results


    # ========================================================
    # DOWNLOAD
    # ========================================================

    def download_document(
        self,
        document
    ):

        url = document[
            "url"
        ]

        print(
            f"Downloading: {url}"
        )

        response = self.session.get(
            url,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        return response.content


    # ========================================================
    # FILE NAME
    # ========================================================

    def build_filename(
        self,
        document,
        content
    ):

        title = (
            document.get(
                "title",
                "lonab_document"
            )
        )

        title = re.sub(
            r"[^a-zA-Z0-9]+",
            "_",
            title
        )

        title = (
            title
            .strip("_")
            .lower()
        )

        digest = hashlib.sha256(
            content
        ).hexdigest()[:12]

        return (
            f"{title}_{digest}.pdf"
        )


    # ========================================================
    # SAVE RAW DOCUMENT
    # ========================================================

    def save_document(
        self,
        document,
        content
    ):

        document_type = (
            document["type"]
        )

        if (
            document_type
            == "program"
        ):

            directory = Path(
                RAW_PROGRAMS_DIR
            )

        elif (
            document_type
            == "result"
        ):

            directory = Path(
                RAW_RESULTS_DIR
            )

        else:

            return None

        filename = (
            self.build_filename(
                document,
                content
            )
        )

        filepath = (
            directory
            / filename
        )

        if not filepath.exists():

            with open(
                filepath,
                "wb"
            ) as file:

                file.write(
                    content
                )

            print(
                f"Saved: {filepath}"
            )

        else:

            print(
                f"Already exists: "
                f"{filepath}"
            )

        return str(
            filepath
        )


    # ========================================================
    # DOWNLOAD PROGRAMS
    # ========================================================

    def collect_programs(self):

        documents = (
            self.get_program_documents()
        )

        collected = []

        for document in documents:

            try:

                content = (
                    self.download_document(
                        document
                    )
                )

                path = (
                    self.save_document(
                        document,
                        content
                    )
                )

                if path:

                    collected.append(
                        {
                            **document,
                            "path": path
                        }
                    )

            except Exception as error:

                print(
                    f"Program error: "
                    f"{error}"
                )

        return collected


    # ========================================================
    # DOWNLOAD RESULTS
    # ========================================================

    def collect_results(self):

        documents = (
            self.get_result_documents()
        )

        collected = []

        for document in documents:

            try:

                content = (
                    self.download_document(
                        document
                    )
                )

                path = (
                    self.save_document(
                        document,
                        content
                    )
                )

                if path:

                    collected.append(
                        {
                            **document,
                            "path": path
                        }
                    )

            except Exception as error:

                print(
                    f"Result error: "
                    f"{error}"
                )

        return collected


    # ========================================================
    # SAVE COLLECTION REPORT
    # ========================================================

    def save_report(
        self,
        programs,
        results
    ):

        report = {

            "source": "LONAB",

            "collected_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),

            "programs": programs,

            "results": results,

        }

        report_path = Path(
            "data/processed"
        ) / (
            "lonab_collection_report.json"
        )

        with open(
            report_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=4
            )

        return str(
            report_path
        )


    # ========================================================
    # FULL COLLECTION
    # ========================================================

    def run(self):

        print(
            "\n"
            "===================================="
        )

        print(
            "LONAB DATA COLLECTION STARTED"
        )

        print(
            "====================================\n"
        )

        programs = (
            self.collect_programs()
        )

        results = (
            self.collect_results()
        )

        report_path = (
            self.save_report(
                programs,
                results
            )
        )

        print(
            "\n"
            "===================================="
        )

        print(
            "LONAB DATA COLLECTION FINISHED"
        )

        print(
            f"Programs: "
            f"{len(programs)}"
        )

        print(
            f"Results: "
            f"{len(results)}"
        )

        print(
            f"Report: "
            f"{report_path}"
        )

        print(
            "====================================\n"
        )

        return {
            "programs": programs,
            "results": results,
            "report": report_path
        }
