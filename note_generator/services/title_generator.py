from __future__ import annotations

import re

from note_generator.models import ClassifiedBookmark, TitledBookmark
from note_generator.services.llm_client import LLMClient


_TITLE_PREFIX_RE = re.compile(r"^(?:標題|title)\s*[:：]\s*", re.IGNORECASE)
_LEADING_WRAP_RE = re.compile(r'^[\s"\'「『（(\[]+')
_TRAILING_WRAP_RE = re.compile(r'[\s"\'」』）)\]]+$')
_LINGORM_NAME_REPLACEMENTS = (
    (re.compile(r"奧姆|欧姆|歐姆"), "Orm"),
    (re.compile(r"玲"), "Ling"),
)


class TitleGenerator:
    def __init__(self, llm_client: LLMClient, model_name: str, max_title_length: int) -> None:
        self._llm_client = llm_client
        self._model_name = model_name
        self._max_title_length = max_title_length

    def generate(self, item: ClassifiedBookmark) -> TitledBookmark:
        prompt = (
            f"請根據以下「{item.category}」類別的 Threads 內容產生一個簡短、自然的繁體中文標題。"
            "只輸出一個標題，不要解釋，不要引號，不要第二行。\n\n"
            "如果內容包含人名或 CP 名稱，例如 Ling、Orm、LingOrm、00k，"
            "請保留原本的拉丁字母寫法，不要翻成中文。\n\n"
            f"{item.enriched.combined_content[:4000]}"
        )
        raw_title = self._llm_client.generate_text(prompt, model_name=self._model_name)
        title = self._clean_title(raw_title)
        if item.category == "LingOrm":
            title = self._restore_lingorm_names(title)
        title = title[: self._max_title_length].strip()
        if not title:
            raise RuntimeError("Gemini returned an empty title")
        return TitledBookmark(
            classified=item,
            generated_title=title,
        )

    def _clean_title(self, raw_title: str) -> str:
        first_line = next((line.strip() for line in raw_title.splitlines() if line.strip()), "")
        without_prefix = _TITLE_PREFIX_RE.sub("", first_line)
        cleaned = _LEADING_WRAP_RE.sub("", without_prefix)
        cleaned = _TRAILING_WRAP_RE.sub("", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _restore_lingorm_names(title: str) -> str:
        restored = title
        for pattern, replacement in _LINGORM_NAME_REPLACEMENTS:
            restored = pattern.sub(replacement, restored)
        return restored
