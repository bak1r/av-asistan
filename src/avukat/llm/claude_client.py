"""Anthropic Claude API istemcisi."""
from __future__ import annotations

from typing import AsyncIterator

import anthropic

from avukat.llm.base import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    """Claude API ile yanıt üretme."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        message = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def generate_stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
