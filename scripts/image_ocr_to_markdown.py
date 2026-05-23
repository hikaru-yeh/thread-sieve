from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib import request

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gemini_client import GeminiClient


DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TRIGGER_CATEGORIES = {"AI", "Claude Code"}
OCR_PROMPT = "請辨識並輸出這張圖片中的所有文字，保留原始排版，不要加任何解釋。"
_OCR_SECTION_RE = re.compile(r"\n*## 圖片文字\n\n.*?(?=\n## |\Z)", re.DOTALL)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_set(value: str, default: set[str]) -> set[str]:
    if not value.strip():
        return set(default)
    return {part.strip() for part in value.split(",") if part.strip()}


def select_trigger_posts(posts: list[dict], classifications: dict, trigger_categories: set[str]) -> list[dict]:
    category_by_key: dict[str, str] = {}
    for item in classifications.get("items", []):
        category = item.get("reason", "")
        for key in (item.get("postId"), item.get("postUrl")):
            if key:
                category_by_key[str(key)] = category

    selected: list[dict] = []
    for post in posts:
        category = category_by_key.get(str(post.get("postId", ""))) or category_by_key.get(str(post.get("postUrl", "")))
        if category in trigger_categories:
            selected.append(post)
    return selected


def find_markdown_by_post_url(markdown_root: Path, post_url: str) -> Path | None:
    if not markdown_root.exists():
        return None
    for path in markdown_root.rglob("*.md"):
        try:
            if post_url in path.read_text(encoding="utf-8"):
                return path
        except OSError:
            continue
    return None


def apply_ocr_section(markdown_path: Path, ocr_texts: list[str]) -> None:
    if not ocr_texts:
        return
    text = markdown_path.read_text(encoding="utf-8")
    text = _OCR_SECTION_RE.sub("", text).rstrip()
    section = "## 圖片文字\n\n" + "\n\n---\n\n".join(t.strip() for t in ocr_texts if t.strip()) + "\n\n"
    sources_index = text.find("## Sources")
    if sources_index == -1:
        updated = text + "\n\n" + section
    else:
        updated = text[:sources_index].rstrip() + "\n\n" + section + text[sources_index:]
    if not updated.endswith("\n"):
        updated += "\n"
    markdown_path.write_text(updated, encoding="utf-8")


def extract_post_image_urls_from_dom_records(records: list[dict]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for record in records:
        src = str(record.get("src") or "")
        width = int(record.get("w") or 0)
        height = int(record.get("h") or 0)
        if "/v/t51.82787-15/" not in src:
            continue
        if width < 200 or height < 250:
            continue
        if src in seen:
            continue
        seen.add(src)
        urls.append(src)
    return urls


def fetch_image_urls_with_playwright(post_url: str, *, headless: bool = True) -> list[str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            records = page.evaluate(
                """() => Array.from(document.images).map((img) => ({
                    src: img.currentSrc || img.src,
                    w: img.naturalWidth,
                    h: img.naturalHeight,
                    alt: img.alt || "",
                }))"""
            )
            return extract_post_image_urls_from_dom_records(records)
        finally:
            browser.close()


def download_image(url: str) -> bytes:
    with request.urlopen(url, timeout=20) as response:
        return response.read()


def ocr_post_images(*, post_url: str, client: GeminiClient, model: str, headless: bool = True) -> list[str]:
    texts: list[str] = []
    for image_url in fetch_image_urls_with_playwright(post_url, headless=headless):
        try:
            text = client.generate_text_from_image(download_image(image_url), OCR_PROMPT, model=model)
        except Exception:
            continue
        if text.strip():
            texts.append(text.strip())
    return texts


def run(
    *,
    input_path: Path,
    classifications_path: Path,
    markdown_root: Path,
    api_key: str,
    model: str,
    trigger_categories: set[str],
    headless: bool,
) -> dict:
    posts = read_json(input_path)
    if not isinstance(posts, list):
        raise ValueError(f"{input_path} must contain a top-level JSON array")
    classifications = read_json(classifications_path)
    if not isinstance(classifications, dict):
        raise ValueError(f"{classifications_path} must contain a JSON object")

    client = GeminiClient(api_key=api_key)
    selected = select_trigger_posts(posts, classifications, trigger_categories)
    updated = 0
    skipped = 0
    for post in selected:
        post_url = str(post.get("postUrl") or "")
        if not post_url:
            skipped += 1
            continue
        markdown_path = find_markdown_by_post_url(markdown_root, post_url)
        if markdown_path is None:
            skipped += 1
            continue
        ocr_texts = ocr_post_images(post_url=post_url, client=client, model=model, headless=headless)
        if not ocr_texts:
            skipped += 1
            continue
        apply_ocr_section(markdown_path, ocr_texts)
        updated += 1

    return {"selected": len(selected), "updated": updated, "skipped": skipped}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR Threads post images and append ## 圖片文字 to markdown notes.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--classifications", required=True)
    parser.add_argument("--markdown-root", required=True)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--trigger-categories", default="")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key.strip():
        print("ERROR: GEMINI_API_KEY missing. Set in .env or pass --api-key.", file=sys.stderr)
        return 2
    model = args.model or os.environ.get("IMAGE_OCR_MODEL", DEFAULT_MODEL)
    trigger_categories = read_csv_set(
        args.trigger_categories or os.environ.get("IMAGE_OCR_CATEGORIES", ""),
        DEFAULT_TRIGGER_CATEGORIES,
    )
    summary = run(
        input_path=Path(args.input),
        classifications_path=Path(args.classifications),
        markdown_root=Path(args.markdown_root),
        api_key=api_key,
        model=model,
        trigger_categories=trigger_categories,
        headless=not args.headed,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
