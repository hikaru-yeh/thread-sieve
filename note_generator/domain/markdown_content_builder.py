from __future__ import annotations

from pathlib import Path

from note_generator.models import MarkdownDocumentOutput, TitledBookmark


def _yaml_str(v: str) -> str:
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'


class MarkdownContentBuilder:
    def build(self, item: TitledBookmark, output_path: Path) -> MarkdownDocumentOutput:
        enriched = item.classified.enriched
        category = item.classified.category
        content_block = enriched.combined_content.strip()
        ocr_texts = item.classified.ocr_texts
        if ocr_texts:
            content_block += "\n\n## 圖片文字\n\n" + "\n\n---\n\n".join(ocr_texts)

        markdown_body = (
            "---\n"
            f"url: {_yaml_str(enriched.source.post_url)}\n"
            f"author: {_yaml_str(enriched.source.author_handle)}\n"
            f"clip_type: {_yaml_str(category)}\n"
            "---\n\n"
            f"{content_block}\n"
        )

        return MarkdownDocumentOutput(
            output_filename=output_path.name,
            output_path=output_path,
            markdown_body=markdown_body,
            category=category,
            source_url=enriched.source.post_url,
            author_handle=enriched.source.author_handle,
        )
