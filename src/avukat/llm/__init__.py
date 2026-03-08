"""LLM istemci factory."""
from __future__ import annotations

from avukat.config import Settings
from avukat.llm.base import BaseLLMClient


def create_llm_client(settings: Settings) -> BaseLLMClient:
    """Ayarlara gore LLM istemcisi olustur."""
    if settings.llm_provider == "ollama":
        from avukat.llm.ollama_client import OllamaClient
        return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model)
    elif settings.llm_provider == "claude":
        from avukat.llm.claude_client import ClaudeClient
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY ayarlanmamis. .env dosyasini kontrol edin.")
        return ClaudeClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    elif settings.llm_provider == "openai":
        from avukat.llm.openai_client import OpenAIClient
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY ayarlanmamis. .env dosyasini kontrol edin.")
        return OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    elif settings.llm_provider == "gemini":
        from avukat.llm.gemini_client import GeminiClient
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY ayarlanmamis. .env dosyasini kontrol edin.")
        return GeminiClient(api_key=settings.google_api_key, model=settings.gemini_model)
    else:
        raise ValueError(f"Bilinmeyen LLM saglayici: {settings.llm_provider}")
