from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from note_generator.infrastructure.anthropic_client import AnthropicClient


def _mk_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_generate_text_returns_text_block():
    with patch("note_generator.infrastructure.anthropic_client.Anthropic") as anthropic_cls:
        sdk = anthropic_cls.return_value
        sdk.messages.create.return_value = _mk_response("Tech")

        client = AnthropicClient(api_key="dummy")
        result = client.generate_text("classify this", model_name="claude-sonnet-4-6")

        assert result == "Tech"
        kwargs = sdk.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["messages"][0]["role"] == "user"
        assert kwargs["messages"][0]["content"] == "classify this"
        assert kwargs["max_tokens"] >= 1024


def test_generate_text_from_image_sends_base64_jpeg():
    with patch("note_generator.infrastructure.anthropic_client.Anthropic") as anthropic_cls:
        sdk = anthropic_cls.return_value
        sdk.messages.create.return_value = _mk_response("hello world")

        client = AnthropicClient(api_key="dummy")
        result = client.generate_text_from_image(b"\xff\xd8jpeg", "ocr this", model_name="claude-sonnet-4-6")

        assert result == "hello world"
        kwargs = sdk.messages.create.call_args.kwargs
        content = kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert content[0]["source"]["data"] == base64.standard_b64encode(b"\xff\xd8jpeg").decode("ascii")
        assert content[1]["type"] == "text"
        assert content[1]["text"] == "ocr this"


def test_missing_api_key_raises():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(api_key="")
