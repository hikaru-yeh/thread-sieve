from pathlib import Path

import scripts.image_ocr_to_markdown as mod


def test_find_markdown_by_post_url_matches_any_markdown_containing_url(tmp_path: Path) -> None:
    first = tmp_path / "first.md"
    nested = tmp_path / "nested"
    nested.mkdir()
    second = nested / "target.md"
    first.write_text("no match", encoding="utf-8")
    second.write_text("來源 https://www.threads.com/@demo/post/ABC123", encoding="utf-8")

    assert mod.find_markdown_by_post_url(tmp_path, "https://www.threads.com/@demo/post/ABC123") == second


def test_apply_ocr_section_inserts_before_sources(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("body\n\n## Sources\n\n- source\n", encoding="utf-8")

    mod.apply_ocr_section(path, ["圖片一", "圖片二"])

    assert path.read_text(encoding="utf-8") == (
        "body\n\n"
        "## 圖片文字\n\n"
        "圖片一\n\n---\n\n圖片二\n\n"
        "## Sources\n\n"
        "- source\n"
    )


def test_apply_ocr_section_replaces_existing_section(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text(
        "body\n\n## 圖片文字\n\nold text\n\n## Sources\n\n- source\n",
        encoding="utf-8",
    )

    mod.apply_ocr_section(path, ["new text"])

    text = path.read_text(encoding="utf-8")
    assert "old text" not in text
    assert text.count("## 圖片文字") == 1
    assert "new text" in text


def test_extract_post_image_urls_from_dom_records_filters_carousel_images() -> None:
    records = [
        {"src": "https://cdn.example/v/t51.82787-19/avatar.jpg", "w": 150, "h": 150},
        {"src": "https://cdn.example/v/t51.82787-15/slide-1.jpg", "w": 224, "h": 280},
        {"src": "https://cdn.example/v/t51.82787-15/slide-1.jpg", "w": 224, "h": 280},
        {"src": "https://cdn.example/v/t51.82787-15/tiny.jpg", "w": 100, "h": 100},
        {"src": "https://cdn.example/v/t51.82787-15/slide-2.jpg", "w": 224, "h": 280},
    ]

    assert mod.extract_post_image_urls_from_dom_records(records) == [
        "https://cdn.example/v/t51.82787-15/slide-1.jpg",
        "https://cdn.example/v/t51.82787-15/slide-2.jpg",
    ]


def test_trigger_items_uses_classification_reasons(tmp_path: Path) -> None:
    posts = [
        {"postId": "p1", "postUrl": "https://threads/p1"},
        {"postId": "p2", "postUrl": "https://threads/p2"},
        {"postId": "p3", "postUrl": "https://threads/p3"},
    ]
    classifications = {
        "items": [
            {"postId": "p1", "postUrl": "https://threads/p1", "reason": "AI"},
            {"postId": "p2", "postUrl": "https://threads/p2", "reason": "Claude Code"},
            {"postId": "p3", "postUrl": "https://threads/p3", "reason": "科技"},
        ]
    }

    result = mod.select_trigger_posts(posts, classifications, {"AI", "Claude Code"})

    assert [post["postId"] for post in result] == ["p1", "p2"]
