from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from note_generator.infrastructure.gemini_client import GeminiClient


@pytest.fixture
def gemini_response():
    response = MagicMock()
    response.text = "AI"
    response.candidates = []
    response.prompt_feedback = None
    return response


def test_generate_text_uses_model_name_keyword(gemini_response):
    with patch("note_generator.infrastructure.gemini_client.genai.Client") as client_cls:
        sdk_client = client_cls.return_value
        sdk_client.models.generate_content.return_value = gemini_response

        client = GeminiClient(api_key="dummy")
        result = client.generate_text("classify this", model_name="gemini-2.5-flash")

        assert result == "AI"
        call_kwargs = sdk_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"
        assert call_kwargs["contents"] == "classify this"


def test_generate_text_from_image_passes_jpeg(gemini_response):
    with patch("note_generator.infrastructure.gemini_client.genai.Client") as client_cls:
        sdk_client = client_cls.return_value
        sdk_client.models.generate_content.return_value = gemini_response

        client = GeminiClient(api_key="dummy")
        result = client.generate_text_from_image(b"jpegbytes", "ocr please", model_name="gemini-2.5-flash")

        assert result == "AI"
        call_args = sdk_client.models.generate_content.call_args.kwargs
        assert call_args["model"] == "gemini-2.5-flash"


def test_missing_api_key_raises():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiClient(api_key="")
