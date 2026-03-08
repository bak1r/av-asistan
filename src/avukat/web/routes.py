"""FastAPI route'ları."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from avukat.rag.pipeline import RAGPipeline

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Ana sayfa."""
    templates = request.app.state.templates
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": request.app.state.settings.app_title,
    })


@router.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    """Soru sor ve yanıt al (HTMX fragment)."""
    templates = request.app.state.templates
    form = await request.form()
    question = form.get("question", "").strip()

    if not question:
        return templates.TemplateResponse("partials/answer.html", {
            "request": request,
            "error": "Lütfen bir soru girin.",
        })

    try:
        # RAG pipeline oluştur
        pipeline = RAGPipeline(
            embedder=request.app.state.embedder,
            llm=request.app.state.llm,
            settings=request.app.state.settings,
        )

        # Veritabanı oturumu ile yanıt üret
        session_factory = request.app.state.session_factory
        async with session_factory() as session:
            response = await pipeline.answer(question, session)

        return templates.TemplateResponse("partials/answer.html", {
            "request": request,
            "answer": response.answer,
            "sources": response.sources,
            "confidence": response.confidence,
            "question": question,
        })

    except Exception as e:
        return templates.TemplateResponse("partials/answer.html", {
            "request": request,
            "error": f"Bir hata oluştu: {str(e)}",
        })


@router.get("/voice", response_class=HTMLResponse)
async def voice_page(request: Request):
    """Sesli asistan sayfasi."""
    settings = request.app.state.settings
    if not settings.voice_enabled:
        return HTMLResponse(
            "<h2>Sesli asistan devre disi.</h2><p>VOICE_ENABLED=true ayarlayin.</p>",
            status_code=403,
        )
    return request.app.state.templates.TemplateResponse("voice.html", {
        "request": request,
        "title": "Sesli Asistan - Avukat AI",
    })


@router.get("/health")
async def health():
    """Saglik kontrolu."""
    return {"status": "ok"}
