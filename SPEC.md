# Spec: Image OCR Enrichment for Threads Markdown Notes

## Objective

Add an image OCR enrichment feature to the existing Threads bookmark pipeline so saved Threads posts that explain AI, agents, or Claude Code mainly through images can produce useful markdown notes.

The user is the local operator of `crawl-the-threads`, who runs one end-to-end workflow:

```text
Threads saved page -> catch.json -> classify + markdown import -> unsave.json + markdown notes
```

The feature should enrich markdown notes for posts classified as `AI` or `Claude Code` by extracting text from attached Threads images with Gemini Vision and appending the extracted text to the generated markdown.

Target pipeline after implementation:

```text
read -> enrich -> classify -> image_ocr_enrich -> title -> build -> write
```

Success means:

- Posts classified as `AI` or `Claude Code` attempt image OCR before title generation and markdown writing.
- Posts in other categories pass through unchanged.
- Posts without images pass through unchanged.
- Any OCR, image fetch, or Threads API failure is soft: the markdown import continues and the item remains unchanged.
- Markdown output includes a `## 圖片文字` section only when OCR text was successfully extracted.
- `crawl-the-threads` continues to orchestrate the watcher and subprocesses without taking ownership of markdown domain logic.

## Tech Stack

Primary repository:

- Path: `D:\shane_yeh\Documents\_Claude_Code\crawl-the-threads`
- Language: Python 3.11+
- Userscript: browser JavaScript via Tampermonkey
- Test framework: `pytest`
- Gemini SDK: `google-genai`

Coupled markdown import repository:

- Path configured by `MARKDOWN_PATH`, currently expected to point at `..\PROJECT_threads-to-note`
- Main entrypoint: `python app.py`
- Existing markdown pipeline owns reader, enricher, classifier, title generation, markdown builder, and writer.

Gemini Vision API boundary:

- Use the existing `google.genai` SDK client.
- For image input, use `google.genai.types.Part.from_bytes(...)`.
- OCR prompt:

```text
請辨識並輸出這張圖片中的所有文字，保留原始排版，不要加任何解釋。
```

## Commands

Run from `crawl-the-threads` project root unless noted.

Create and activate local venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run all current tests:

```powershell
pytest tests/
```

Run classifier unit tests:

```powershell
pytest tests/test_classify_to_scribe_ai.py -v
```

Run watcher tests:

```powershell
pytest tests/test_watch_pipeline.py -v
```

Run userscript smoke probe:

```powershell
python scripts/agent_driver.py probe
```

Deploy userscript after editing `userscripts/threads-scriber-auto.user.js`:

```powershell
python scripts/push_userscript.py --probe
```

Run markdown import tests from the note project when implementing the OCR side there:

```powershell
cd ..\PROJECT_threads-to-note
pytest tests/ -v
```

Run the watched end-to-end local pipeline:

```powershell
.\start_pipeline.ps1
```

## Project Structure

`crawl-the-threads`:

```text
scripts/watch_pipeline.py
  Orchestrates the local file watcher. Starts the classifier job and the markdown note job.

scripts/classify_to_scribe_ai.py
  Classifies scraped posts and writes unsave.json for the userscript unsave flow.

scripts/_gemini_client.py
  Gemini text-classification boundary for crawl-the-threads.

userscripts/threads-scriber-auto.user.js
  Browser userscript that scrapes saved Threads posts and auto-loads unsave.json.

tests/
  Pure Python tests for classifier, watcher, agent driver, and pipeline output.

classify_config.json
  Category list, unsaved categories, and classifier hints.

.env / .env.example
  Local runtime configuration. Secrets stay in .env only.
```

`PROJECT_threads-to-note` integration points:

```text
models.py
  Add or preserve ClassifiedBookmark.ocr_texts: list[str].

services/llm_client.py
  Add generate_text_from_image(...) for Gemini Vision OCR.

services/image_ocr_enricher.py
  New service that fetches Threads image URLs, downloads images, runs OCR, and returns an enriched ClassifiedBookmark.

domain/markdown_content_builder.py
  Append the optional ## 圖片文字 section.

config.py
  Add OCR model, enabled flag, and trigger category configuration.

workflows/import_bookmarks_to_markdown.py
  Wire image_ocr_enrich between classify and title generation.

tests/
  Unit tests for models, LLM image method, OCR enricher, markdown builder, config, and workflow ordering.
```

## Code Style

Prefer small service boundaries and dataclass pass-throughs. Do not make OCR part of classification or title generation.

Example shape for the OCR category guard:

```python
OCR_PROMPT = "請辨識並輸出這張圖片中的所有文字，保留原始排版，不要加任何解釋。"


class ImageOCREnricher:
    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str,
        trigger_categories: set[str],
    ) -> None:
        self._llm_client = llm_client
        self._model_name = model_name
        self._trigger_categories = trigger_categories

    def enrich(self, item: ClassifiedBookmark) -> ClassifiedBookmark:
        if item.category not in self._trigger_categories:
            return item

        try:
            image_urls = self._fetch_image_urls(item.enriched.source.post_url)
        except Exception as error:
            logger.warning("Image OCR skipped for %s: %s", item.enriched.source.post_url, error)
            return item

        ocr_texts: list[str] = []
        for url in image_urls:
            try:
                image_bytes = self._download_image(url)
                text = self._llm_client.generate_text_from_image(
                    image_bytes,
                    OCR_PROMPT,
                    model_name=self._model_name,
                )
            except Exception as error:
                logger.warning("Image OCR failed for %s: %s", url, error)
                continue

            if text.strip():
                ocr_texts.append(text.strip())

        if not ocr_texts:
            return item

        return replace(item, ocr_texts=ocr_texts)
```

Conventions:

- Match the existing Python style: explicit dataclasses, small pure helpers, direct `Path` usage, no speculative framework.
- Keep failures soft inside `ImageOCREnricher.enrich(...)`; callers should not need OCR-specific error handling.
- Keep environment parsing in config code, not scattered through services.
- Keep Windows paths in `.toml` single-quoted if any TOML file is touched.
- Do not hardcode secrets, API keys, tokens, passwords, or absolute filesystem paths in source.
- Prefer relative paths and environment variables in examples and configuration.

## Functional Design

### Trigger Categories

Default trigger categories:

```text
AI,Claude Code
```

Recommended config:

```text
THREADS_IMAGE_OCR_ENABLED=true
THREADS_GEMINI_OCR_MODEL=gemini-2.5-flash
THREADS_IMAGE_OCR_CATEGORIES=AI,Claude Code
```

If `THREADS_IMAGE_OCR_ENABLED=false`, the workflow must use a disabled pass-through enricher.

If `THREADS_IMAGE_OCR_CATEGORIES` is blank or absent, default to `AI,Claude Code`.

### Image Fetching

The OCR service should fetch image URLs from the Threads post page/API layer already identified in the existing design from `PROJECT_threads-to-note`:

- Extract shortcode from Threads URL.
- Resolve Threads media payload.
- Support carousel images through `carousel_media`.
- Support single images through `image_versions2`.
- Select the highest-resolution candidate per image where dimensions are available.

The service should not save images locally.

### Gemini OCR

Add one LLM client method in the markdown project:

```python
def generate_text_from_image(
    self,
    image_bytes: bytes,
    prompt: str,
    *,
    model_name: str,
) -> str:
    ...
```

Expected behavior:

- Send image bytes and OCR prompt to Gemini.
- Use temperature `0`.
- Return stripped text.
- Return `""` for empty Gemini text.
- Log empty responses at warning level.

### Markdown Output

If OCR texts exist, append them after the original combined content:

```markdown
原文或回覆文字...

## 圖片文字

第一張圖片 OCR 文字

---

第二張圖片 OCR 文字
```

No `## 圖片文字` section should appear when `ocr_texts` is empty.

### Watcher Integration

`crawl-the-threads/scripts/watch_pipeline.py` should remain an orchestrator.

Current watcher starts:

- `scripts/classify_to_scribe_ai.py` for `unsave.json`
- `python app.py` in `MARKDOWN_PATH` for markdown notes

The OCR behavior should be implemented inside the markdown project subprocess. `watch_pipeline.py` should only need changes if it must forward or document additional environment variables explicitly.

## Testing Strategy

Use test-driven implementation for the OCR feature.

Tests in `PROJECT_threads-to-note`:

- `tests/test_models.py`
  - `ClassifiedBookmark.ocr_texts` defaults to `[]`.

- `tests/test_llm_client.py`
  - `generate_text_from_image(...)` sends image bytes through `types.Part.from_bytes(...)`.
  - Empty Gemini response returns `""` and logs a warning.

- `tests/test_image_ocr_enricher.py`
  - Non-trigger categories pass through unchanged.
  - `AI` triggers OCR.
  - `Claude Code` triggers OCR.
  - No images returns unchanged.
  - One image returns one OCR text.
  - Multiple images collect multiple OCR texts.
  - One failing image is skipped while later images continue.
  - Blank OCR output is excluded.
  - Fetch/API failures are soft and return unchanged.

- `tests/test_markdown_content_builder.py`
  - `ocr_texts=[]` does not append `## 圖片文字`.
  - One OCR text appends `## 圖片文字`.
  - Multiple OCR texts are separated by `---`.

- `tests/test_config.py`
  - OCR enabled defaults to true.
  - OCR can be disabled.
  - OCR model defaults to `gemini-2.5-flash`.
  - Trigger categories default to `{"AI", "Claude Code"}`.
  - Trigger categories can be overridden from comma-separated env.

- `tests/test_workflow.py`
  - Workflow calls OCR after classify and before title.
  - `from_config(...)` wires enabled and disabled OCR enrichers correctly.

Tests in `crawl-the-threads`:

- Existing `pytest tests/` must remain green.
- Add watcher tests only if `watch_pipeline.py` changes behavior.
- Do not add fake DOM assertions for userscript-only behavior; use `agent_driver.py probe` for userscript smoke checks.

Manual verification:

- Run a scrape that includes at least one image-heavy `AI` or `Claude Code` post.
- Confirm markdown contains original content plus `## 圖片文字`.
- Confirm `unsave.json` generation still works.
- Confirm non-trigger categories do not get OCR sections.

## Boundaries

Always:

- Keep OCR failures soft.
- Keep markdown writing logic in `PROJECT_threads-to-note`.
- Keep `crawl-the-threads` focused on scraping, classification for unsave, userscript automation, and subprocess orchestration.
- Use `.env`, config objects, or environment variables for runtime settings.
- Add regression tests before production code changes.
- Use Context7 for library/API documentation before implementing or changing Gemini SDK calls.
- Run relevant tests before claiming completion.

Ask first:

- Editing `README.md`.
- Moving markdown generation logic into `crawl-the-threads`.
- Changing the `catch.json` schema emitted by the userscript.
- Changing `unsave.json` schema consumed by the userscript.
- Adding new third-party dependencies.
- Saving downloaded images to disk.
- Reclassifying posts after OCR.
- Changing the classifier category taxonomy.
- Making OCR trigger for categories beyond `AI` and `Claude Code`.

Never:

- Hardcode API keys, secrets, tokens, passwords, or machine-specific absolute paths in source.
- Commit `.env` secrets.
- Make OCR failure fail the whole markdown import.
- Paste manually into Tampermonkey after userscript edits; use `python scripts/push_userscript.py --probe`.
- Edit README as part of this spec-only step.
- Rewrite unrelated pipeline, userscript, or markdown logic while implementing OCR.

## Implementation Plan

1. Complete OCR data model and config in `PROJECT_threads-to-note`.
   - Add `ocr_texts` if missing.
   - Add OCR enabled flag, model field, and trigger category field.
   - Verify with config and model tests.

2. Add Gemini image generation boundary.
   - Implement `LLMClient.generate_text_from_image(...)`.
   - Verify with mocked Gemini client tests.

3. Add `ImageOCREnricher`.
   - Implement shortcode/media extraction helpers.
   - Implement image download and Gemini OCR loop.
   - Enforce `AI` and `Claude Code` trigger categories.
   - Verify with unit tests and soft-failure tests.

4. Append OCR text in markdown builder.
   - Add `## 圖片文字` section only when `ocr_texts` exists.
   - Verify with markdown builder tests.

5. Wire workflow order.
   - Add OCR enricher protocol/stub.
   - Wire `classify -> ocr_enrich -> title`.
   - Verify order with workflow tests.

6. Re-run current `crawl-the-threads` tests.
   - Confirm orchestration and classifier behavior still pass.
   - Add watcher tests only if watcher code changed.

7. Perform manual smoke verification.
   - Run `python scripts/agent_driver.py probe`.
   - Run a small scrape or use a known fixture/manual sample.
   - Confirm markdown output and `unsave.json`.

## Success Criteria

- `pytest tests/ -v` passes in `PROJECT_threads-to-note`.
- `pytest tests/` passes in `crawl-the-threads`.
- A post classified as `AI` with image media produces markdown containing `## 圖片文字`.
- A post classified as `Claude Code` with image media produces markdown containing `## 圖片文字`.
- A post classified as any other category does not call Gemini Vision OCR.
- A post with no images does not add an OCR section.
- OCR errors are logged but do not increment workflow failure count.
- The watcher still produces both `unsave.json` and markdown notes.
- No README edits happen until the user explicitly confirms the README update plan.

## Open Questions

- Should OCR trigger categories be strictly configurable in `PROJECT_threads-to-note`, or should `crawl-the-threads` also expose/pass a namespaced env var for convenience?
- Should OCR text influence generated titles, or should title generation continue to use only the original/reply-enriched text plus OCR-enriched classified object? The proposed pipeline puts OCR before title, so title may see OCR if title generation reads combined content from the classified item in the future.
- Should duplicate text between original post content and OCR output be removed, or is preserving raw OCR output preferable for now?
- Should Threads image fetching use only the GraphQL/media API path, or should it fall back to parsing post HTML if the API shape changes?

