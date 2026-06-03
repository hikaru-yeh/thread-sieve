from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from note_generator.models import SourceBookmark


class BookmarkReader:
    def __init__(self, input_path: Path) -> None:
        self._input_path = input_path

    def read(self) -> list[SourceBookmark]:
        raw_data = json.loads(self._input_path.read_text(encoding="utf-8"))
        if not isinstance(raw_data, list):
            raise ValueError("Bookmark export must be a JSON list of records")
        return [
            item
            for item in (self._normalize_record(record) for record in raw_data)
            if item is not None
        ]

    def _normalize_record(self, record: object) -> SourceBookmark | None:
        if not isinstance(record, dict):
            return None

        post_url = self._read_first(record, "postUrl", "source_url")
        author_handle = self._read_first(record, "authorHandle", "author_handle")
        content_text = self._read_first(record, "contentText", "content")

        if not post_url or not author_handle or not content_text:
            return None

        metadata: dict[str, Any] = {
            key: value
            for key, value in record.items()
            if key
            not in {
                "postUrl",
                "source_url",
                "authorHandle",
                "author_handle",
                "contentText",
                "content",
            }
        }
        return SourceBookmark(
            post_url=post_url,
            author_handle=author_handle,
            content_text=content_text,
            metadata=metadata,
        )

    @staticmethod
    def _read_first(record: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
