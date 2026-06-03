from __future__ import annotations

from dataclasses import replace
import json
import logging
import re
from typing import Protocol
from urllib import parse, request

from note_generator.models import ClassifiedBookmark
from note_generator.services.llm_client import LLMClient


logger = logging.getLogger(__name__)

OCR_PROMPT = "請辨識並輸出這張圖片中的所有文字，保留原始排版，不要加任何解釋。"
_SHORTCODE_RE = re.compile(r"/post/([A-Za-z0-9_-]+)")
_SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_THREADS_GRAPHQL_URL = "https://www.threads.com/api/graphql/"
_THREADS_MEDIA_DOC_ID = "26994965700190837"


class ImagePageClient(Protocol):
    def fetch_image_urls(self, url: str) -> list[str]:
        ...


class ImageOCREnricher:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_name: str,
        trigger_categories: set[str],
        image_page_client: ImagePageClient | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._model_name = model_name
        self._trigger_categories = trigger_categories
        self._image_page_client = image_page_client

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

    def _fetch_image_urls(self, post_url: str) -> list[str]:
        shortcode = self._extract_shortcode(post_url)
        post_id = self._shortcode_to_post_id(shortcode)
        try:
            return self._extract_image_urls(self._request_post_payload(post_id))
        except Exception:
            if self._image_page_client is None:
                raise
            image_urls = self._image_page_client.fetch_image_urls(post_url)
            if not image_urls:
                raise RuntimeError("No images found in rendered post page")
            return image_urls

    @staticmethod
    def _request_post_payload(post_id: str) -> dict:
        variables = json.dumps({"postID": post_id}, separators=(",", ":"))
        body = parse.urlencode({"doc_id": _THREADS_MEDIA_DOC_ID, "variables": variables}).encode("utf-8")
        req = request.Request(
            _THREADS_GRAPHQL_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _extract_shortcode(post_url: str) -> str:
        match = _SHORTCODE_RE.search(post_url)
        if not match:
            raise RuntimeError(f"Could not extract shortcode from Threads post URL: {post_url}")
        return match.group(1)

    @staticmethod
    def _shortcode_to_post_id(shortcode: str) -> str:
        value = 0
        for char in shortcode:
            index = _SHORTCODE_ALPHABET.find(char)
            if index < 0:
                raise RuntimeError(f"Invalid Threads shortcode character: {char!r}")
            value = value * 64 + index
        return str(value)

    @staticmethod
    def _extract_image_urls(payload: dict) -> list[str]:
        media = payload.get("data", {}).get("media", {})
        image_items = media.get("carousel_media") or [media]

        urls: list[str] = []
        for item in image_items:
            candidates = item.get("image_versions2", {}).get("candidates", [])
            candidates = [candidate for candidate in candidates if candidate.get("url")]
            if not candidates:
                continue
            best = max(candidates, key=lambda candidate: candidate.get("width") or 0)
            urls.append(best["url"])

        if not urls:
            raise RuntimeError("No images found in post payload")
        return urls

    @staticmethod
    def _download_image(url: str) -> bytes:
        with request.urlopen(url, timeout=20) as response:
            return response.read()
