from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic LLM boundary used by ThreadSieve service-layer generators."""

    def generate_text(self, prompt: str, *, model_name: str) -> str:
        """Return a deterministic text completion. Implementations should set temperature=0."""
        ...

    def generate_text_from_image(self, image_bytes: bytes, prompt: str, *, model_name: str) -> str:
        """Return an OCR / vision completion for a single JPEG/PNG image."""
        ...
