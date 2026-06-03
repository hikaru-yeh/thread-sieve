from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import re

from note_generator.models import EnrichedBookmark, SourceBookmark


class ThreadPageClient(Protocol):
    def fetch_body_text(self, url: str) -> str:
        """Fetch visible page body text for a thread URL."""

    def fetch_image_urls(self, url: str) -> list[str]:
        """Fetch visible post image URLs for a thread URL."""


COOKIE_SELECTORS = [
    "button:has-text('Decline optional cookies')",
    "button:has-text('Allow all cookies')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    "button:has-text('Allow all')",
    "button:has-text('Only allow essential cookies')",
    "button:has-text('Continue without logging in')",
    "button:has-text('Not now')",
    "[role='button']:has-text('Accept')",
]

PRIMARY_CONTENT_STOP_MARKERS = [
    "TranslateLike",
    "Translate Like",
    "Log in to see more replies.",
    "Related threads",
    "Threads TermsPrivacy Policy",
]

PRIMARY_CONTENT_STOP_LINES = {
    "Translate",
    "Related threads",
    "Log in to see more replies.",
}

AUTHOR_BLOCK_METADATA_LINES = {
    "·",
    "Author",
}

DEFAULT_PRE_CONTENT_LABEL_LINES = {
    "Verified",
}


@dataclass
class PlaywrightThreadPageClient:
    headless: bool = True

    def fetch_body_text(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                dismiss_overlays(page)
                page.wait_for_timeout(1000)
                return page.inner_text("body")
            finally:
                browser.close()

    def fetch_image_urls(self, url: str) -> list[str]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                )
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                dismiss_overlays(page)
                page.wait_for_timeout(1000)
                records = page.evaluate(
                    """() => Array.from(document.images).map((img) => ({
                        src: img.currentSrc || img.src,
                        w: img.naturalWidth,
                        h: img.naturalHeight,
                        alt: img.alt || "",
                    }))"""
                )
                return extract_post_image_urls_from_image_records(records)
            finally:
                browser.close()


class ThreadsReplyEnricher:
    def __init__(self, page_client: ThreadPageClient, pre_content_label_lines: set[str] | None = None) -> None:
        self._page_client = page_client
        self._pre_content_label_lines = set(DEFAULT_PRE_CONTENT_LABEL_LINES)
        if pre_content_label_lines is not None:
            self._pre_content_label_lines.update(pre_content_label_lines)

    def enrich(self, source: SourceBookmark) -> EnrichedBookmark:
        primary_content = source.content_text.strip()

        try:
            body_text = self._page_client.fetch_body_text(source.post_url)
        except Exception:
            return EnrichedBookmark(
                source=source,
                primary_content=primary_content,
                author_replies=[],
                reply_fetch_status="fallback_to_primary",
            )

        primary_content = self._extract_primary_content(
            body_text=body_text,
            seed_content=primary_content,
            author_handle=source.author_handle,
        )
        author_replies = self._extract_author_replies(
            body_text=body_text,
            author_handle=source.author_handle,
            primary_content=primary_content,
        )
        if not author_replies:
            return EnrichedBookmark(
                source=source,
                primary_content=primary_content,
                author_replies=[],
                reply_fetch_status="no_author_replies",
            )

        return EnrichedBookmark(
            source=source,
            primary_content=primary_content,
            author_replies=author_replies,
            reply_fetch_status="fetched",
        )

    def _extract_author_replies(
        self,
        *,
        body_text: str,
        author_handle: str,
        primary_content: str,
    ) -> list[str]:
        normalized_handle = author_handle.strip().lstrip("@").lower()
        if not normalized_handle:
            return []

        replies: list[str] = []
        normalized_primary = primary_content.strip()
        for candidate in self._extract_author_blocks(
            body_text=body_text,
            author_handle=normalized_handle,
        ):
            if not candidate or candidate == normalized_primary:
                continue
            replies.append(candidate)

        return replies

    def _extract_primary_content(
        self,
        *,
        body_text: str,
        seed_content: str,
        author_handle: str,
    ) -> str:
        seed_candidates = self._seed_candidates(seed_content)
        if not seed_candidates:
            return seed_content.strip()
        normalized_seed = seed_candidates[0]

        normalized_handle = author_handle.strip().lstrip("@").lower()
        if normalized_handle:
            author_blocks = self._extract_author_blocks(
                body_text=body_text,
                author_handle=normalized_handle,
            )
            for candidate in author_blocks:
                if candidate and any(seed in candidate for seed in seed_candidates):
                    return candidate
            if author_blocks:
                return author_blocks[0]

        normalized_body = body_text.replace("\xa0", " ")
        normalized_lines = self._normalize_body_lines(normalized_body)
        start_line_index = next(
            (
                index
                for index, line in enumerate(normalized_lines)
                if any(seed in line for seed in seed_candidates)
            ),
            -1,
        )
        if start_line_index == -1:
            matching_seed = next(
                (seed for seed in seed_candidates if seed and seed in normalized_body),
                "",
            )
            start_index = normalized_body.find(matching_seed) if matching_seed else -1
            if start_index == -1:
                return normalized_seed

            candidate = normalized_body[start_index:]
            stop_indexes = [
                candidate.find(marker)
                for marker in PRIMARY_CONTENT_STOP_MARKERS
                if candidate.find(marker) != -1
            ]
            if stop_indexes:
                candidate = candidate[: min(stop_indexes)]

            candidate_lines = [line.strip() for line in candidate.splitlines() if line.strip()]
            extracted = "\n".join(candidate_lines).strip()
            if not extracted:
                return normalized_seed
            return extracted

        first_line = normalized_lines[start_line_index]
        matching_seed = next(
            (seed for seed in seed_candidates if seed and seed in first_line),
            normalized_seed,
        )
        first_line_start = first_line.find(matching_seed)
        content_lines = [first_line[first_line_start:].strip()]

        for index in range(start_line_index + 1, len(normalized_lines)):
            line = normalized_lines[index]
            if line in PRIMARY_CONTENT_STOP_LINES:
                break
            if line.startswith("© ") or line.startswith("Threads Terms"):
                break
            if self._looks_like_metric(line):
                continue
            if self._is_probable_new_comment_start(normalized_lines, index):
                break

            trimmed_line = line
            inline_stop_indexes = [
                trimmed_line.find(marker)
                for marker in PRIMARY_CONTENT_STOP_MARKERS
                if trimmed_line.find(marker) != -1
            ]
            if inline_stop_indexes:
                trimmed_line = trimmed_line[: min(inline_stop_indexes)].rstrip()
                if trimmed_line:
                    content_lines.append(trimmed_line)
                break

            content_lines.append(trimmed_line)

        extracted = "\n".join(line for line in content_lines if line).strip()
        if not extracted:
            return normalized_seed
        return extracted

    def _extract_author_blocks(self, *, body_text: str, author_handle: str) -> list[str]:
        legacy_blocks = self._extract_author_blocks_from_split_blocks(
            body_text=body_text,
            author_handle=author_handle,
        )
        if legacy_blocks:
            return legacy_blocks

        lines = self._normalize_body_lines(body_text)
        if not lines or not author_handle:
            return []

        blocks: list[str] = []
        index = 0
        while index < len(lines):
            if self._normalize_handle(lines[index]) != author_handle:
                index += 1
                continue

            cursor = index + 1
            while (
                cursor + 1 < len(lines)
                and self._looks_like_timestamp(lines[cursor + 1])
                and (
                    lines[cursor] in self._pre_content_label_lines
                    or self._looks_like_plain_handle(lines[cursor])
                )
            ):
                cursor += 1
            if cursor < len(lines) and self._looks_like_timestamp(lines[cursor]):
                cursor += 1

            while cursor < len(lines) and lines[cursor] in AUTHOR_BLOCK_METADATA_LINES:
                cursor += 1

            content_lines: list[str] = []
            while cursor < len(lines):
                line = lines[cursor]

                if line == "Related threads":
                    break
                if line in PRIMARY_CONTENT_STOP_LINES:
                    cursor += 1
                    continue
                if line.startswith("© ") or line.startswith("Threads Terms"):
                    break
                if line in AUTHOR_BLOCK_METADATA_LINES:
                    cursor += 1
                    continue
                if self._looks_like_metric(line):
                    cursor += 1
                    continue
                if self._is_probable_new_comment_start(lines, cursor):
                    break

                content_lines.append(line)
                cursor += 1

            text = "\n".join(content_lines).strip()
            if text:
                blocks.append(text)
            index = cursor

        return blocks

    def _extract_author_blocks_from_split_blocks(
        self,
        *,
        body_text: str,
        author_handle: str,
    ) -> list[str]:
        blocks: list[str] = []
        for block in self._split_blocks(body_text):
            header, *content_lines = block
            if not self._is_handle_marker(header):
                continue
            if self._normalize_handle(header) != author_handle:
                continue

            cursor = 0
            while cursor < len(content_lines):
                line = content_lines[cursor].strip()
                if line in self._pre_content_label_lines:
                    cursor += 1
                    continue
                if self._looks_like_timestamp(line):
                    cursor += 1
                    continue
                if line in AUTHOR_BLOCK_METADATA_LINES:
                    cursor += 1
                    continue
                break

            candidate = "\n".join(line.rstrip() for line in content_lines[cursor:]).strip()
            if candidate:
                blocks.append(candidate)

        return blocks

    @staticmethod
    def _split_blocks(body_text: str) -> list[list[str]]:
        blocks: list[list[str]] = []
        current_block: list[str] = []
        pending_blank_lines = 0

        for raw_line in body_text.splitlines():
            stripped_line = raw_line.strip()
            if not stripped_line:
                pending_blank_lines += 1
                continue

            if current_block:
                if pending_blank_lines == 1:
                    current_block.append("")
                elif pending_blank_lines >= 2:
                    blocks.append(current_block)
                    current_block = []

            current_block.append(stripped_line)
            pending_blank_lines = 0

        if current_block:
            blocks.append(current_block)

        return blocks

    @staticmethod
    def _normalize_handle(line: str) -> str:
        stripped = line.strip()
        if ThreadsReplyEnricher._is_handle_marker(stripped):
            return stripped.lstrip("@").lower()
        if ThreadsReplyEnricher._looks_like_plain_handle(stripped):
            return stripped.lower()
        return ""

    @staticmethod
    def _is_handle_marker(line: str) -> bool:
        return bool(re.fullmatch(r"@[A-Za-z0-9._]+", line.strip()))

    @staticmethod
    def _seed_candidates(seed_content: str) -> list[str]:
        normalized_seed = seed_content.strip()
        if not normalized_seed:
            return []

        candidates = [normalized_seed]
        lines = [line.rstrip() for line in normalized_seed.splitlines()]
        while lines and re.fullmatch(r"\d+/\d+", lines[-1].strip()):
            lines.pop()

        if lines:
            lines[-1] = re.sub(r"(?:[\s\xa0])+\d+/\d+\s*$", "", lines[-1]).rstrip()
            while lines and not lines[-1].strip():
                lines.pop()

        cleaned_seed = "\n".join(line for line in lines if line.strip()).strip()
        if cleaned_seed and cleaned_seed not in candidates:
            candidates.append(cleaned_seed)

        return candidates

    @staticmethod
    def _normalize_body_lines(body_text: str) -> list[str]:
        return [line.strip() for line in body_text.splitlines() if line.strip()]

    @staticmethod
    def _looks_like_timestamp(line: str) -> bool:
        lowered = line.strip().lower()
        return bool(
            re.fullmatch(r"\d{2}/\d{2}/\d{2}", line.strip())
            or re.fullmatch(r"\d+[smhdwy](?:\s+edited)?", lowered)
        )

    @staticmethod
    def _looks_like_metric(line: str) -> bool:
        return bool(re.fullmatch(r"[0-9.]+[kKmM]?", line.strip()))

    @staticmethod
    def _looks_like_plain_handle(line: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9._]{2,32}", line.strip()))

    @classmethod
    def _is_probable_new_comment_start(cls, lines: list[str], index: int) -> bool:
        line = lines[index]
        if not cls._normalize_handle(line):
            return False

        lookahead = lines[index + 1 : index + 4]
        if any(cls._looks_like_timestamp(candidate) for candidate in lookahead):
            return True
        if lookahead and all(
            cls._looks_like_metric(candidate) or cls._looks_like_plain_handle(candidate)
            for candidate in lookahead[:2]
        ):
            return True
        return False


def dismiss_overlays(page: object) -> None:
    for selector in COOKIE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=1000):
                locator.click(timeout=1500)
                return
        except Exception:
            continue


def extract_post_image_urls_from_image_records(records: list[dict]) -> list[str]:
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
