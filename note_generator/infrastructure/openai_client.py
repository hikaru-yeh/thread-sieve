from __future__ import annotations

import base64
import logging
import time

from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIClient:
    """LLMClient adapter for OpenAI ChatGPT (text + vision)."""

    def __init__(
        self,
        api_key: str,
        *,
        max_retries: int = 2,
        retry_base_delay: float = 1.5,
    ) -> None:
        if not api_key.strip():
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI backend")
        self._client = OpenAI(api_key=api_key)
        self._max_retries = max(0, max_retries)
        self._retry_base_delay = retry_base_delay

    def generate_text(self, prompt: str, *, model_name: str) -> str:
        def _call() -> str:
            response = self._client.chat.completions.create(
                model=model_name,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            choice = (response.choices or [None])[0]
            text = (getattr(getattr(choice, "message", None), "content", "") or "").strip()
            if not text:
                logger.warning("OpenAI returned empty text response")
            return text

        return self._with_retries(_call, label="OpenAI")

    def generate_text_from_image(self, image_bytes: bytes, prompt: str, *, model_name: str) -> str:
        encoded = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{encoded}"
        # No retry wrapper — matches GeminiClient.generate_text_from_image parity (single-shot OCR).
        response = self._client.responses.create(
            model=model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )
        text = (getattr(response, "output_text", "") or "").strip()
        if not text:
            logger.warning("OpenAI Vision returned empty response for image OCR")
        return text

    def _with_retries(self, call, *, label: str) -> str:
        attempt = 0
        last_error: Exception | None = None
        while attempt <= self._max_retries:
            try:
                return call()
            except Exception as error:
                last_error = error
                attempt += 1
                if attempt > self._max_retries:
                    break
                delay = self._retry_base_delay * attempt
                logger.warning("%s call failed (attempt %d): %s. Retrying in %.1fs", label, attempt, error, delay)
                time.sleep(delay)
        assert last_error is not None
        raise last_error
