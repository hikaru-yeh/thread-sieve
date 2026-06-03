from __future__ import annotations

import logging

from note_generator.config import load_config
from note_generator.workflows.import_bookmarks_to_markdown import ImportBookmarksToMarkdownWorkflow


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    configure_logging()
    config = load_config()
    workflow = ImportBookmarksToMarkdownWorkflow.from_config(config)
    summary = workflow.run()
    logging.getLogger(__name__).info(
        "Import complete: processed=%s written=%s skipped=%s failed=%s",
        summary.processed_count,
        summary.written_count,
        summary.skipped_count,
        summary.failed_count,
    )


if __name__ == "__main__":
    main()
