"""FastAPI uygulama factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from avukat.config import Settings
from avukat.db import init_db, get_session_factory
from avukat.ingestion.embedder import ArticleEmbedder
from avukat.llm import create_llm_client

WEB_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlatma ve kapanma işlemleri."""
    settings: Settings = app.state.settings
    # Veritabanını hazırla
    await init_db(settings)
    app.state.session_factory = get_session_factory(settings)

    # Embedder'ı yükle
    app.state.embedder = ArticleEmbedder(settings.embedding_model)

    # LLM istemcisini oluştur
    app.state.llm = create_llm_client(settings)

    yield


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluştur."""
    settings = Settings()

    app = FastAPI(
        title=settings.app_title,
        lifespan=lifespan,
    )

    app.state.settings = settings

    # Static dosyalar
    static_dir = WEB_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Templates
    templates_dir = WEB_DIR / "templates"
    templates_dir.mkdir(exist_ok=True)
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Route'ları kaydet
    from avukat.web.routes import router
    app.include_router(router)

    return app
