"""Ollama LLM istemcisi (yerel, ücretsiz)."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from avukat.llm.base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Ollama API ile yerel LLM kullanımı."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str, system: str | None = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": False,
        }
        resp = await self.client.post(f"{self.base_url}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"]

    async def generate_stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": True,
        }
        async with self.client.stream("POST", f"{self.base_url}/api/generate", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line:
                    data = json.loads(line)
                    if not data.get("done"):
                        yield data.get("response", "")
