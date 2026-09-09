import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config.race_sources import race_sources


class LonabScraper:
    """
    Discovers publicly available race programs and results
    published on the official LONAB website.

    This class handles discovery and downloading.

    Parsing the detailed contents of PDFs and race pages
    is handled separately by the processing layer.
    """

    def __init__(self):

        self.base_url = race_sources.LONAB_BASE_URL

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": race_sources.USER_AGENT,
                "Accept-Language": "fr,en;q=0.8",
            }
        )

    def _get(self, url):

        response = self.session.get(
            url,
            timeout=race_sources.REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return response

    def _clean_text(self, value):

        return re.sub(
            r"\s+",
            " ",
            value or "",
        ).strip()

    def discover_posts(self, pages=None):
        """
        Search LONAB listing pages and return links
        that appear related to horse-racing programs
        or results.
        """

        if pages is None:
            pages = race_sources.DISCOVERY_PAGES

        discovered = []
        seen_urls = set()

        keywords = [
            "journal hippique",
            "pmu",
            "pmu'b",
            "pmub",
            "récapitulatif des arrivées",
            "recapitulatif des arrivees",
            "résultats",
            "resultats",
        ]

        for page_number in range(pages):

            url = f"{self.base_url}/fr/node?page={page_number}"

            print(
                f"Checking LONAB archive page {page_number}: {url}"
            )

            try:

                response = self._get(url)

                soup = BeautifulSoup(
                    response.text,
                    "lxml",
                )

                for link in soup.find_all("a", href=True):

                    title = self._clean_text(
                        link.get_text(" ", strip=True)
                    )

                    href = link["href"]

                    combined_text = title.lower()

                    if not any(
                        keyword in combined_text
                        for keyword in keywords
                    ):
                        continue

                    absolute_url = urljoin(
                        self.base_url,
                        href,
                    )

                    if absolute_url in seen_urls:
                        continue

                    seen_urls.add(absolute_url)

                    post_type = self.classify_post(
                        title
                    )

                    discovered.append(
                        {
                            "title": title,
                            "url": absolute_url,
                            "type": post_type,
                            "source": "LONAB",
                        }
                    )

                time.sleep(1)

            except Exception as error:

                print(
                    f"Failed to inspect page "
                    f"{page_number}: {error}"
                )

        return discovered

    def classify_post(self, title):
        """
        Classify a discovered LONAB post.
        """

        value = title.lower()

        if (
            "journal hippique" in value
            or "programme" in value
        ):
            return "program"

        if (
            "récapitulatif" in value
            or "recapitulatif" in value
        ):
            return "result"

        if (
            "résultats" in value
            or "resultats" in value
        ):
            return "result"

        return "unknown"

    def extract_document_links(self, post_url):
        """
        Open a LONAB post and find downloadable documents,
        especially PDF files.
        """

        print(
            f"Opening LONAB post: {post_url}"
        )

        response = self._get(post_url)

        soup = BeautifulSoup(
            response.text,
            "lxml",
        )

        documents = []

        seen_urls = set()

        for link in soup.find_all(
            "a",
            href=True,
        ):

            href = link["href"]

            absolute_url = urljoin(
                self.base_url,
                href,
            )

            link_text = self._clean_text(
                link.get_text(" ", strip=True)
            )

            is_pdf = (
                ".pdf" in absolute_url.lower()
            )

            if not is_pdf:
                continue

            if absolute_url in seen_urls:
                continue

            seen_urls.add(
                absolute_url
            )

            documents.append(
                {
                    "url": absolute_url,
                    "name": link_text,
                    "type": "pdf",
                }
            )

        return documents

    def download_document(
        self,
        document_url,
    ):
        """
        Download a document and return its raw bytes.
        """

        print(
            f"Downloading: {document_url}"
        )

        response = self._get(
            document_url
        )

        return response.content

    def discover_race_documents(
        self,
        pages=None,
    ):
        """
        Complete discovery process.

        Returns race-related posts together
        with any downloadable PDF documents.
        """

        posts = self.discover_posts(
            pages=pages
        )

        records = []

        for post in posts:

            try:

                documents = (
                    self.extract_document_links(
                        post["url"]
                    )
                )

                records.append(
                    {
                        **post,
                        "documents": documents,
                    }
                )

                time.sleep(1)

            except Exception as error:

                print(
                    f"Could not inspect "
                    f"{post['url']}: {error}"
                )

        return records
