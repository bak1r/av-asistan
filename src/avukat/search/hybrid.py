"""Hibrit arama: vektör + BM25 sonuçlarını Reciprocal Rank Fusion ile birleştirme."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from avukat.models import SearchResult
from avukat.search.vector_search import vector_search
from avukat.search.bm25_search import bm25_search


def reciprocal_rank_fusion(
    vector_results: list[SearchResult],
    bm25_results: list[SearchResult],
    k: int = 60,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[SearchResult]:
    """RRF ile iki sonuç listesini birleştir."""
    scores: dict[int, float] = {}
    article_map: dict[int, SearchResult] = {}

    for rank, result in enumerate(vector_results, start=1):
        scores[result.article_id] = scores.get(result.article_id, 0) + vector_weight / (k + rank)
        article_map[result.article_id] = result

    for rank, result in enumerate(bm25_results, start=1):
        scores[result.article_id] = scores.get(result.article_id, 0) + bm25_weight / (k + rank)
        if result.article_id not in article_map:
            article_map[result.article_id] = result

    sorted_ids = sorted(scores, key=lambda aid: scores[aid], reverse=True)
    return [
        SearchResult(
            article_id=aid,
            law_number=article_map[aid].law_number,
            law_name=article_map[aid].law_name,
            article_number=article_map[aid].article_number,
            title=article_map[aid].title,
            text=article_map[aid].text,
            score=scores[aid],
            source="hybrid",
        )
        for aid in sorted_ids
    ]


async def hybrid_search(
    session: AsyncSession,
    query_embedding: list[float],
    query_text: str,
    top_k: int = 10,
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4,
) -> list[SearchResult]:
    """Hibrit arama: vektör + BM25 → RRF fusion."""
    # Her iki aramayı çalıştır
    vec_results = await vector_search(session, query_embedding, top_k=top_k * 2)
    bm25_results = await bm25_search(session, query_text, top_k=top_k * 2)

    # RRF ile birleştir
    fused = reciprocal_rank_fusion(
        vec_results, bm25_results,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
    )

    return fused[:top_k]
