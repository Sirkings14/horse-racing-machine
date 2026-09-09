import hashlib
from pathlib import Path
from datetime import datetime, timezone


class DocumentStore:
    """
    Stores raw documents downloaded from LONAB.

    The original documents are preserved so that
    the machine can always trace processed data
    back to its source.
    """

    def __init__(self):

        self.base_directory = Path(
            "data/raw"
        )

    def _safe_filename(
        self,
        value,
    ):

        cleaned = []

        for character in value:

            if (
                character.isalnum()
                or character in (
                    "-",
                    "_",
                    ".",
                )
            ):

                cleaned.append(
                    character
                )

            else:

                cleaned.append(
                    "_"
                )

        return "".join(
            cleaned
        )

    def save_document(
        self,
        content,
        source_url,
        category,
        original_name="",
    ):
        """
        Save a downloaded document.

        Returns metadata describing the
        stored file.
        """

        digest = hashlib.sha256(
            content
        ).hexdigest()

        extension = ".pdf"

        if original_name:

            name = self._safe_filename(
                original_name
            )

        else:

            name = digest

        if not name.lower().endswith(
            extension
        ):

            name = (
                f"{name}{extension}"
            )

        category_directory = (
            self.base_directory
            / category
        )

        category_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_path = (
            category_directory
            / name
        )

        if not file_path.exists():

            with open(
                file_path,
                "wb",
            ) as file:

                file.write(
                    content
                )

        return {
            "path": str(
                file_path
            ),
            "sha256": digest,
            "source_url": source_url,
            "stored_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }
