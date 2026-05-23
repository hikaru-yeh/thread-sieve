# Spec: Crawl-Owned Threads Image OCR

## Objective

`crawl-the-threads` owns the complete local workflow:

```text
Threads saved scrape -> catch.json -> classify -> unsave.json
                         |
                         -> markdown writer subprocess -> markdown notes
                         |
                         -> crawl-owned image OCR -> ## 圖片文字
```

The OCR feature enriches markdown notes for image-heavy Threads posts classified as `AI` or `Claude Code`. It must live in this repository, not in the legacy `PROJECT_threads-to-note` codebase.

Success means:

- OCR code, config, tests, and docs are in `crawl-the-threads`.
- The watcher runs OCR after both classifier and markdown subprocess finish.
- OCR reads `catch.json` and `unsave.json`, selects `AI` / `Claude Code`, renders each Threads post, OCRs attached images with Gemini Vision, and inserts `## 圖片文字` into the matching markdown file.
- Failures are soft: missing markdown, missing images, download errors, and Gemini OCR errors skip that item without failing the whole pipeline.

## Tech Stack

- Python 3.11+
- `google-genai` for Gemini text and image OCR
- Playwright Python for rendered Threads post image discovery
- `pytest` for tests
- Existing Tampermonkey userscript remains the scrape source
- Legacy markdown writer may still run as a subprocess, but OCR is not implemented there

## Commands

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Run watcher:

```powershell
.\start_pipeline.ps1
```

Run OCR manually:

```powershell
python scripts/image_ocr_to_markdown.py `
  --input data/catch.json `
  --classifications data/unsave.json `
  --markdown-root D:\path\to\markdown-root
```

Run tests:

```powershell
pytest tests/
```

## Project Structure

```text
scripts/watch_pipeline.py
  Watches catch.json, runs classifier + markdown writer, then runs OCR.

scripts/classify_to_scribe_ai.py
  Produces unsave.json with classification reasons.

scripts/image_ocr_to_markdown.py
  Crawl-owned OCR step. Selects trigger posts, discovers images, OCRs them, and patches markdown notes.

scripts/_gemini_client.py
  Shared Gemini client, including image input support.

tests/test_image_ocr_to_markdown.py
  OCR selection, markdown matching, section replacement, DOM image filtering.

tests/test_watch_pipeline.py
  Watcher orchestration, including OCR step ordering.
```

## Code Style

Keep this boring and explicit:

```python
selected = select_trigger_posts(posts, classifications, {"AI", "Claude Code"})
for post in selected:
    markdown_path = find_markdown_by_post_url(markdown_root, post["postUrl"])
    if markdown_path is None:
        continue
    ocr_texts = ocr_post_images(post_url=post["postUrl"], client=client, model=model)
    apply_ocr_section(markdown_path, ocr_texts)
```

Conventions:

- Use environment variables for runtime paths and models.
- Do not hardcode secrets or machine-specific output paths.
- Keep OCR failures soft.
- Keep markdown matching simple: scan markdown files for the exact `postUrl`.
- Replace an existing `## 圖片文字` section instead of duplicating it.
- Avoid changing the legacy markdown writer for OCR behavior.

## Configuration

`crawl-the-threads/.env`:

```dotenv
MARKDOWN_OUTPUT_PATH=
IMAGE_OCR_ENABLED=true
IMAGE_OCR_MODEL=gemini-2.5-flash
IMAGE_OCR_CATEGORIES=AI,Claude Code
```

If `MARKDOWN_OUTPUT_PATH` is blank, `watch_pipeline.py` tries to read `THREADS_MARKDOWN_OUTPUT` from `MARKDOWN_PATH\.env`.

## Runtime Flow

1. Userscript writes `catch.json`.
2. Watcher starts `classify_to_scribe_ai.py` and the markdown subprocess.
3. Watcher waits for both jobs.
4. Watcher resolves markdown output root.
5. Watcher starts `scripts/image_ocr_to_markdown.py`.
6. OCR script:
   - reads posts from `catch.json`;
   - reads classification reasons from `unsave.json`;
   - selects posts whose reason is in `IMAGE_OCR_CATEGORIES`;
   - renders each Threads post with Playwright;
   - filters carousel image URLs from `document.images`;
   - sends each image to Gemini Vision;
   - inserts or replaces `## 圖片文字` before `## Sources`.

## Testing Strategy

Unit tests cover:

- selecting trigger posts from `catch.json` + `unsave.json`;
- finding markdown files by exact post URL;
- inserting `## 圖片文字` before `## Sources`;
- replacing an existing `## 圖片文字` section;
- filtering rendered DOM image records to carousel image URLs;
- watcher launching OCR after classifier and notes jobs finish.

Manual smoke tests:

- Run `scripts/image_ocr_to_markdown.py` against a known image-heavy Threads post.
- Confirm `images=N`, Gemini OCR text is written, and the markdown note has one `## 圖片文字` section.

## Boundaries

Always:

- Keep this feature in `crawl-the-threads`.
- Use TDD for behavior changes.
- Keep OCR failures soft.
- Run `pytest tests/` before claiming completion.

Ask first:

- Moving markdown generation itself into `crawl-the-threads`.
- Changing `catch.json` or `unsave.json` schemas.
- Reclassifying posts after OCR.
- Saving image files locally.

Never:

- Hardcode API keys or secrets.
- Require modifications to the legacy `PROJECT_threads-to-note` project for OCR.
- Duplicate `## 圖片文字` sections.

