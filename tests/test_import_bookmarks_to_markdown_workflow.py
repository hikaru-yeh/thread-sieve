from __future__ import annotations

import json
from pathlib import Path

from note_generator.domain.markdown_content_builder import MarkdownContentBuilder
from note_generator.models import (
    ClassifiedBookmark,
    EnrichedBookmark,
    MarkdownDocumentOutput,
    SourceBookmark,
    TitledBookmark,
)
from note_generator.workflows.import_bookmarks_to_markdown import ImportBookmarksToMarkdownWorkflow


class FakeReader:
    def __init__(self, items: list[SourceBookmark]) -> None:
        self.items = items

    def read(self) -> list[SourceBookmark]:
        return self.items


class FakeEnricher:
    def enrich(self, source: SourceBookmark) -> EnrichedBookmark:
        return EnrichedBookmark(source=source, primary_content=source.content_text)


class FakeClassifier:
    def __init__(self, categories_by_post_id: dict[str, str]) -> None:
        self.categories_by_post_id = categories_by_post_id
        self.calls: list[str] = []

    def classify(self, item: EnrichedBookmark) -> ClassifiedBookmark:
        post_id = str(item.source.metadata["postId"])
        self.calls.append(post_id)
        return ClassifiedBookmark(
            enriched=item,
            category=self.categories_by_post_id[post_id],
            category_reason="test",
        )


class FakeOcrEnricher:
    def enrich(self, item: ClassifiedBookmark) -> ClassifiedBookmark:
        return item


class FakeTitleGenerator:
    def generate(self, item: ClassifiedBookmark) -> TitledBookmark:
        post_id = str(item.enriched.source.metadata["postId"])
        return TitledBookmark(classified=item, generated_title=f"title-{post_id}")


class FakeFilenameBuilder:
    def build(self, title: str) -> str:
        return f"{title}.md"


class FakeWriter:
    def write(self, document: MarkdownDocumentOutput) -> Path:
        document.output_path.parent.mkdir(parents=True, exist_ok=True)
        document.output_path.write_text(document.markdown_body, encoding="utf-8")
        return document.output_path


class FakeEventLogger:
    def emit(self, event_type: str, **details: object) -> None:
        pass


def test_workflow_writes_markdown_and_unsave_from_one_classification_pass(tmp_path: Path) -> None:
    output_dir = tmp_path / "notes"
    unsave_path = tmp_path / "unsave.json"
    items = [
        SourceBookmark(
            post_url="https://threads/post/1",
            author_handle="@demo",
            content_text="AI topic",
            metadata={"postId": "p_ai"},
        ),
        SourceBookmark(
            post_url="https://threads/post/2",
            author_handle="@demo",
            content_text="Food topic",
            metadata={"postId": "p_food"},
        ),
    ]
    classifier = FakeClassifier({"p_ai": "AI", "p_food": "Food"})
    workflow = ImportBookmarksToMarkdownWorkflow(
        reader=FakeReader(items),
        enricher=FakeEnricher(),
        classifier=classifier,
        ocr_enricher=FakeOcrEnricher(),
        title_generator=FakeTitleGenerator(),
        filename_builder=FakeFilenameBuilder(),
        content_builder=MarkdownContentBuilder(),
        writer=FakeWriter(),
        output_dir=output_dir,
        event_logger=FakeEventLogger(),
        unsaved_categories={"AI"},
        unsave_output_path=unsave_path,
        source_file_name="catch.json",
        classification_model="test-model",
    )

    summary = workflow.run()

    assert summary.written_count == 2
    assert classifier.calls == ["p_ai", "p_food"]
    assert (output_dir / "title-p_ai.md").exists()
    assert (output_dir / "title-p_food.md").exists()

    payload = json.loads(unsave_path.read_text(encoding="utf-8"))
    assert payload["sourceFile"] == "catch.json"
    assert payload["unsavedCategories"] == ["AI"]
    assert payload["summary"] == {
        "total": 2,
        "ai": 1,
        "not_ai": 1,
        "unsure": 0,
        "failed": 0,
    }
    assert payload["items"][0]["postId"] == "p_ai"
    assert payload["items"][0]["reason"] == "AI"
