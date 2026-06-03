from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import backfill_image_ocr as mod  # noqa: E402


def note(*, status: str = "stub", url_key: str = "網址", url: str = "https://www.threads.com/@demo/post/ABC") -> str:
    return (
        "---\n"
        f"status: {status}\n"
        f"{url_key}: {url}\n"
        "---\n\n"
        "short body\n\n"
        "## Sources\n\n"
        "- source\n"
    )


def test_extract_frontmatter_url_supports_chinese_and_url_keys() -> None:
    assert mod.extract_frontmatter_url(note(url_key="網址", url="https://threads/chinese")) == "https://threads/chinese"
    assert mod.extract_frontmatter_url(note(url_key="url", url="https://threads/url")) == "https://threads/url"


def test_extract_frontmatter_url_prefers_chinese_key_and_strips_quotes() -> None:
    markdown = (
        "---\n"
        '網址: "https://threads/chinese"\n'
        "url: 'https://threads/url'\n"
        "---\n\n"
        "body\n"
    )

    assert mod.extract_frontmatter_url(markdown) == "https://threads/chinese"


def test_missing_url_becomes_skip_decision() -> None:
    markdown = "---\nstatus: stub\n---\n\nshort body\n"

    decision = mod.decide_note(markdown, min_content_chars=800, force=False)

    assert decision.status == "skipped"
    assert decision.reason == "missing_url"


def test_insert_image_text_section_before_sources() -> None:
    markdown = "body\n\n## Sources\n\n- source\n"

    updated = mod.insert_image_text_section(markdown, ["圖片一", "圖片二"])

    assert updated == (
        "body\n\n"
        "## 圖片文字\n\n"
        "### 圖片 1\n\n"
        "圖片一\n\n"
        "### 圖片 2\n\n"
        "圖片二\n\n"
        "## Sources\n\n"
        "- source\n"
    )


def test_insert_image_text_section_appends_when_sources_absent() -> None:
    assert mod.insert_image_text_section("body\n", ["圖片一"]) == (
        "body\n\n"
        "## 圖片文字\n\n"
        "### 圖片 1\n\n"
        "圖片一\n"
    )


def test_replace_image_text_section_only_when_force() -> None:
    markdown = "body\n\n## 圖片文字\n\nold\n\n## Sources\n\n- source\n"

    assert mod.insert_image_text_section(markdown, ["new"], force=False) == markdown
    forced = mod.insert_image_text_section(markdown, ["new"], force=True)

    assert "old" not in forced
    assert forced.count("## 圖片文字") == 1
    assert "new" in forced
    assert "## Sources" in forced


def test_skip_existing_image_text_section_by_default_and_force_allows_candidate() -> None:
    markdown = note() + "\n## 圖片文字\n\nold\n"

    skipped = mod.decide_note(markdown, min_content_chars=800, force=False)
    forced = mod.decide_note(markdown, min_content_chars=800, force=True)

    assert skipped.status == "skipped"
    assert skipped.reason == "already_has_image_text"
    assert forced.status == "candidate"
    assert forced.reason == "eligible"


def test_dry_run_does_not_fetch_or_write_candidates(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    original = note()
    target.write_text(original, encoding="utf-8")
    log_path = tmp_path / "backfill.jsonl"
    calls: list[str] = []

    def discover_images(post_url: str, *, headless: bool) -> list[str]:
        calls.append(post_url)
        return ["https://image"]

    summary = mod.run_batch(
        path=tmp_path,
        log_path=log_path,
        dry_run=True,
        discover_images=discover_images,
        ocr_image=lambda image_url: "text",
    )

    assert calls == []
    assert target.read_text(encoding="utf-8") == original
    assert summary["scanned"] == 1
    assert summary["processed"] == 1
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["status"] == "processed"
    assert events[0]["reason"] == "dry_run_candidate"


def test_dry_run_does_not_require_ocr_configuration(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text(note(), encoding="utf-8")

    summary = mod.run_batch(path=tmp_path, log_path=tmp_path / "backfill.jsonl", dry_run=True)

    assert summary["processed"] == 1


def test_chandra_backend_can_be_selected_without_gemini_api_key(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target.md"
    target.write_text(note(), encoding="utf-8")

    calls: list[dict[str, object]] = []

    def fake_build_ocr_image(**kwargs: object):
        calls.append(kwargs)
        return lambda image_url: "Chandra OCR text"

    monkeypatch.setattr(mod, "build_ocr_image", fake_build_ocr_image)

    summary = mod.run_batch(
        path=tmp_path,
        log_path=tmp_path / "backfill.jsonl",
        discover_images=lambda post_url, *, headless: ["https://image"],
        ocr_backend="chandra",
    )

    assert summary["processed"] == 1
    assert "Chandra OCR text" in target.read_text(encoding="utf-8")
    assert calls[0]["backend"] == "chandra"


def test_default_backend_is_gemini(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target.md"
    target.write_text(note(), encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_build_ocr_image(**kwargs: object):
        calls.append(kwargs)
        return lambda image_url: "Gemini OCR text"

    monkeypatch.setattr(mod, "build_ocr_image", fake_build_ocr_image)

    summary = mod.run_batch(
        path=tmp_path,
        log_path=tmp_path / "backfill.jsonl",
        discover_images=lambda post_url, *, headless: ["https://image"],
        api_key="key",
    )

    assert summary["processed"] == 1
    assert calls[0]["backend"] == "gemini"


def test_batch_summary_counts_processed_skipped_failed_and_no_images(tmp_path: Path) -> None:
    processed = tmp_path / "processed.md"
    skipped = tmp_path / "skipped.md"
    no_images = tmp_path / "no_images.md"
    failed = tmp_path / "failed.md"
    processed.write_text(note(url="https://threads/processed"), encoding="utf-8")
    skipped.write_text(note(status="complete", url="https://threads/skipped"), encoding="utf-8")
    no_images.write_text(note(url="https://threads/no-images"), encoding="utf-8")
    failed.write_text(note(url="https://threads/failed"), encoding="utf-8")
    log_path = tmp_path / "backfill.jsonl"

    def discover_images(post_url: str, *, headless: bool) -> list[str]:
        if post_url.endswith("/processed"):
            return ["https://image/1"]
        if post_url.endswith("/no-images"):
            return []
        raise RuntimeError("fetch failed")

    summary = mod.run_batch(
        path=tmp_path,
        log_path=log_path,
        discover_images=discover_images,
        ocr_image=lambda image_url: "OCR text",
    )

    assert summary == {
        "scanned": 4,
        "processed": 1,
        "skipped": 1,
        "no_images": 1,
        "failed": 1,
        "log": str(log_path),
    }
    assert "## 圖片文字" in processed.read_text(encoding="utf-8")
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert sorted(event["status"] for event in events) == ["failed", "no_images", "processed", "skipped"]
