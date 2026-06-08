from __future__ import annotations

from note_generator.services.llm_client import LLMClient


class _FakeClient:
    def generate_text(self, prompt: str, *, model_name: str) -> str:
        return f"text:{model_name}:{prompt[:8]}"

    def generate_text_from_image(self, image_bytes: bytes, prompt: str, *, model_name: str) -> str:
        return f"image:{model_name}:{len(image_bytes)}"


def test_fake_client_satisfies_protocol():
    client: LLMClient = _FakeClient()  # type: ignore[assignment]
    assert client.generate_text("hello world", model_name="m") == "text:m:hello wo"
    assert client.generate_text_from_image(b"xxx", "p", model_name="m") == "image:m:3"


def test_protocol_methods_are_declared():
    assert hasattr(LLMClient, "generate_text")
    assert hasattr(LLMClient, "generate_text_from_image")
