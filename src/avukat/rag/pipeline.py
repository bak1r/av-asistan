"""Tam RAG pipeline: soru → arama → bağlam → LLM → doğrulama → yanıt."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from avukat.config import Settings
from avukat.models import RAGResponse, SearchResult
from avukat.ingestion.embedder import ArticleEmbedder
from avukat.llm.base import BaseLLMClient
from avukat.llm.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from avukat.search.hybrid import hybrid_search
from avukat.rag.citation import CitationVerifier


class RAGPipeline:
    """Hukuki soru-cevap pipeline."""

    def __init__(
        self,
        embedder: ArticleEmbedder,
        llm: BaseLLMClient,
        settings: Settings,
    ):
        self.embedder = embedder
        self.llm = llm
        self.settings = settings
        self.verifier = CitationVerifier()

    async def answer(self, question: str, session: AsyncSession) -> RAGResponse:
        """Soruyu yanıtla: arama → bağlam → üret → doğrula."""
        # 1. Soruyu embedle
        query_vec = self.embedder.embed_query(question).tolist()

        # 2. Hibrit arama
        results = await hybrid_search(
            session=session,
            query_embedding=query_vec,
            query_text=question,
            top_k=self.settings.search_top_k,
            vector_weight=self.settings.hybrid_vector_weight,
            bm25_weight=self.settings.hybrid_bm25_weight,
        )

        # 3. Bağlam oluştur (ilk 5 sonuç)
        top_results = results[:5]
        context = self._build_context(top_results)

        # 4. LLM ile yanıt üret
        prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)
        raw_answer = await self.llm.generate(prompt, system=SYSTEM_PROMPT)

        # 5. Kaynak doğrulama
        sources, invalid, confidence = self.verifier.verify(raw_answer, top_results)

        return RAGResponse(
            question=question,
            answer=raw_answer,
            sources=sources,
            confidence=confidence,
            search_results=top_results,
        )

    def _build_context(self, results: list[SearchResult]) -> str:
        """Arama sonuçlarından LLM bağlamı oluştur."""
        if not results:
            return "Kaynak bulunamadı."

        parts = []
        for i, r in enumerate(results, 1):
            law_label = "TCK" if r.law_number == 5237 else "CMK"
            header = f"[Kaynak {i}] {law_label} Madde {r.article_number}"
            if r.title:
                header += f" - {r.title}"
            parts.append(f"{header}:\n{r.text}")

        return "\n\n---\n\n".join(parts)
