from __future__ import annotations

import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin Gemini boundary shared by service-layer generators."""

    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise RuntimeError("GEMINI_API_KEY is required for classification and title generation")
        self._client = genai.Client(api_key=api_key)

    def generate_text(self, prompt: str, *, model_name: str) -> str:
        response = self._client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        if not response.text:
            candidates = getattr(response, "candidates", None) or []
            for i, candidate in enumerate(candidates):
                finish_reason = getattr(candidate, "finish_reason", "unknown")
                safety_ratings = getattr(candidate, "safety_ratings", [])
                logger.warning(
                    "Gemini empty response: candidate[%d] finish_reason=%r safety_ratings=%r",
                    i, finish_reason, safety_ratings,
                )
            if not candidates:
                logger.warning("Gemini empty response: no candidates. prompt_feedback=%r",
                               getattr(response, "prompt_feedback", None))
        return (response.text or "").strip()

    def generate_text_from_image(self, image_bytes: bytes, prompt: str, *, model_name: str) -> str:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        response = self._client.models.generate_content(
            model=model_name,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(temperature=0),
        )
        if not response.text:
            logger.warning("Gemini Vision returned empty response for image OCR")
        return (response.text or "").strip()
