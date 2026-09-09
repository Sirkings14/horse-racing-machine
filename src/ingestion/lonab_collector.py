from src.ingestion.lonab_scraper import (
    LonabScraper,
)

from src.ingestion.document_store import (
    DocumentStore,
)


class LonabCollector:
    """
    Downloads newly discovered LONAB race documents
    into the machine's raw historical storage.
    """

    def __init__(self):

        self.scraper = LonabScraper()

        self.store = DocumentStore()

    def collect(
        self,
        pages=None,
    ):

        records = (
            self.scraper.discover_race_documents(
                pages=pages
            )
        )

        collected = []

        for record in records:

            category = (
                "historical"
                if record["type"]
                == "result"
                else "upcoming"
            )

            for document in (
                record["documents"]
            ):

                try:

                    content = (
                        self.scraper.download_document(
                            document["url"]
                        )
                    )

                    stored = (
                        self.store.save_document(
                            content=content,
                            source_url=document[
                                "url"
                            ],
                            category=category,
                            original_name=document[
                                "name"
                            ],
                        )
                    )

                    collected.append(
                        {
                            "post": record[
                                "title"
                            ],
                            "post_type": record[
                                "type"
                            ],
                            "document": document[
                                "url"
                            ],
                            "stored": stored,
                        }
                    )

                except Exception as error:

                    print(
                        f"Download failed: "
                        f"{document['url']}"
                    )

                    print(error)

        return collected
