from __future__ import annotations

from pathlib import Path

from note_generator.models import MarkdownDocumentOutput


class MarkdownWriter:
    def __init__(self, dry_run: bool) -> None:
        self._dry_run = dry_run

    def write(self, document: MarkdownDocumentOutput) -> Path:
        if self._dry_run:
            return document.output_path

        document.output_path.parent.mkdir(parents=True, exist_ok=True)
        document.output_path.write_text(document.markdown_body, encoding="utf-8")
        return document.output_path
