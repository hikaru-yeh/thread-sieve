from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceBookmark:
    post_url: str
    author_handle: str
    content_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnrichedBookmark:
    source: SourceBookmark
    primary_content: str
    author_replies: list[str] = field(default_factory=list)
    combined_content: str = ""
    reply_fetch_status: str = "no_author_replies"

    def __post_init__(self) -> None:
        if self.combined_content:
            return

        parts = [self.primary_content.strip()]
        parts.extend(reply.strip() for reply in self.author_replies if reply.strip())
        combined = "\n\n".join(part for part in parts if part)
        object.__setattr__(self, "combined_content", combined)


@dataclass(frozen=True)
class ClassifiedBookmark:
    enriched: EnrichedBookmark
    category: str
    category_reason: str | None = None
    ocr_texts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TitledBookmark:
    classified: ClassifiedBookmark
    generated_title: str
    resolved_filename: str | None = None


@dataclass(frozen=True)
class MarkdownDocumentOutput:
    output_filename: str
    output_path: Path
    markdown_body: str
    category: str
    source_url: str
    author_handle: str


@dataclass(frozen=True)
class ImportSummary:
    processed_count: int
    written_count: int
    skipped_count: int
    failed_count: int
