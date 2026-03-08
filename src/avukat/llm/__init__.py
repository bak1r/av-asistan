"""LLM istemci factory."""
from __future__ import annotations

from avukat.config import Settings
from avukat.llm.base import BaseLLMClient


def create_llm_client(settings: Settings) -> BaseLLMClient:
    """Ayarlara göre LLM istemcisi oluştur."""
    if settings.llm_provider == "ollama":
        from avukat.llm.ollama_client import OllamaClient
        return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model)
    elif settings.llm_provider == "claude":
        from avukat.llm.claude_client import ClaudeClient
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY ayarlanmamış. .env dosyasını kontrol edin.")
        return ClaudeClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    elif settings.llm_provider == "openai":
        from avukat.llm.openai_client import OpenAIClient
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY ayarlanmamış. .env dosyasını kontrol edin.")
        return OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
    else:
        raise ValueError(f"Bilinmeyen LLM sağlayıcı: {settings.llm_provider}")
