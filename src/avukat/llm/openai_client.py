"""OpenAI API istemcisi."""
from __future__ import annotations

from typing import AsyncIterator

from openai import AsyncOpenAI

from avukat.llm.base import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    """OpenAI API ile yanıt üretme."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    async def generate_stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=2048,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
