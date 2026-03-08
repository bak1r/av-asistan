"""Soyut LLM arayüzü."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMClient(ABC):
    """Tüm LLM istemcileri bu arayüzü uygulamalı."""

    @abstractmethod
    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Tek seferde tam yanıt üret."""
        ...

    @abstractmethod
    async def generate_stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        """Token token yanıt üret (streaming)."""
        ...
