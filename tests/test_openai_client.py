from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from note_generator.infrastructure.openai_client import OpenAIClient


def _chat_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


def _responses_response(text: str) -> MagicMock:
    response = MagicMock()
    response.output_text = text
    return response


def test_generate_text_uses_chat_completions():
    with patch("note_generator.infrastructure.openai_client.OpenAI") as openai_cls:
        sdk = openai_cls.return_value
        sdk.chat.completions.create.return_value = _chat_response("AI")

        client = OpenAIClient(api_key="dummy")
        result = client.generate_text("classify this", model_name="gpt-4o-mini")

        assert result == "AI"
        kwargs = sdk.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["temperature"] == 0
        assert kwargs["messages"][0]["role"] == "user"
        assert kwargs["messages"][0]["content"] == "classify this"


def test_generate_text_from_image_uses_responses_api_with_data_url():
    with patch("note_generator.infrastructure.openai_client.OpenAI") as openai_cls:
        sdk = openai_cls.return_value
        sdk.responses.create.return_value = _responses_response("hello world")

        client = OpenAIClient(api_key="dummy")
        result = client.generate_text_from_image(b"\xff\xd8jpeg", "ocr this", model_name="gpt-4o")

        assert result == "hello world"
        kwargs = sdk.responses.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o"
        content = kwargs["input"][0]["content"]
        assert content[0]["type"] == "input_text"
        assert content[0]["text"] == "ocr this"
        assert content[1]["type"] == "input_image"
        expected_b64 = base64.standard_b64encode(b"\xff\xd8jpeg").decode("ascii")
        assert content[1]["image_url"] == f"data:image/jpeg;base64,{expected_b64}"
        assert content[1]["detail"] == "auto"


def test_missing_api_key_raises():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIClient(api_key="")
