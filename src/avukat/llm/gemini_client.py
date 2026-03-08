"""Google Gemini API istemcisi (text mode)."""
from __future__ import annotations

from typing import AsyncIterator

from google import genai

from avukat.llm.base import BaseLLMClient


class GeminiClient(BaseLLMClient):
    """Gemini API ile yakit uretme."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str, system: str | None = None) -> str:
        config = {}
        if system:
            config["system_instruction"] = system
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text

    async def generate_stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        config = {}
        if system:
            config["system_instruction"] = system
        async for chunk in self.client.aio.models.generate_content_stream(
            model=self.model,
            contents=prompt,
            config=config,
        ):
            if chunk.text:
                yield chunk.text
