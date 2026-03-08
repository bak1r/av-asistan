from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# .env dosyasını proje kökünden bul
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # Veritabanı
    database_url: str = "postgresql+asyncpg://avukat:avukat_dev_123@localhost:5432/avukat"

    # Embedding
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = 384

    # LLM
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    gemini_live_model: str = "gemini-2.0-flash-exp"

    # Arama
    search_top_k: int = 10
    hybrid_vector_weight: float = 0.4
    hybrid_bm25_weight: float = 0.6

    # Voice
    voice_enabled: bool = False
    voice_language: str = "tr"
    voice_max_session_minutes: int = 30

    # Browser
    browser_enabled: bool = False
    browser_headless: bool = True

    # Memory
    memory_enabled: bool = True

    # Uygulama
    app_title: str = "Avukat AI"
    debug: bool = False

    @model_validator(mode="after")
    def _fill_empty_keys_from_dotenv(self):
        """Bos env var'lari .env dosyasindan doldur."""
        if _ENV_FILE.exists():
            from dotenv import dotenv_values
            dotenv = dotenv_values(_ENV_FILE)
            for field in (
                "anthropic_api_key", "openai_api_key", "google_api_key",
                "database_url", "llm_provider",
            ):
                if not getattr(self, field) and dotenv.get(field.upper()):
                    object.__setattr__(self, field, dotenv[field.upper()])
        return self

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}
