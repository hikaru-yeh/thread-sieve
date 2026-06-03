from __future__ import annotations

from note_generator.models import EnrichedBookmark, SourceBookmark
from note_generator.services.category_classifier import CategoryClassifier
from note_generator.services.threads_reply_enricher import ThreadsReplyEnricher


class FakeLLMClient:
    def __init__(self, category: str) -> None:
        self.category = category
        self.prompts: list[str] = []

    def generate_text(self, prompt: str, *, model_name: str) -> str:
        self.prompts.append(prompt)
        return self.category


def test_category_classifier_uses_config_categories_and_hints() -> None:
    client = FakeLLMClient("Custom")
    classifier = CategoryClassifier(
        llm_client=client,  # type: ignore[arg-type]
        model_name="test-model",
        categories=["Custom", "Other"],
        hints=["Custom hint"],
    )
    item = EnrichedBookmark(
        source=SourceBookmark(
            post_url="https://threads/post/1",
            author_handle="@demo",
            content_text="custom topic",
        ),
        primary_content="custom topic",
    )

    classified = classifier.classify(item)

    assert classified.category == "Custom"
    assert "可選分類：Custom、Other" in client.prompts[0]
    assert "- Custom hint" in client.prompts[0]


def test_threads_reply_enricher_accepts_configured_label_lines() -> None:
    class FakePageClient:
        def fetch_body_text(self, url: str) -> str:
            return "@demo\nCustom\n1h\nUseful reply"

        def fetch_image_urls(self, url: str) -> list[str]:
            return []

    enricher = ThreadsReplyEnricher(
        page_client=FakePageClient(),
        pre_content_label_lines={"Custom"},
    )

    enriched = enricher.enrich(
        SourceBookmark(
            post_url="https://threads/post/1",
            author_handle="@demo",
            content_text="Useful reply",
        )
    )

    assert enriched.primary_content == "Useful reply"

