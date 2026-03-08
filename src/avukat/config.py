from pydantic_settings import BaseSettings


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

    # Arama
    search_top_k: int = 10
    hybrid_vector_weight: float = 0.6
    hybrid_bm25_weight: float = 0.4

    # Uygulama
    app_title: str = "Avukat AI"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
