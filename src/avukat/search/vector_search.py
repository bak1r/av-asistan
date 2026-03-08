"""pgvector cosine similarity araması."""
from __future__ import annotations

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from avukat.models import SearchResult


async def vector_search(
    session: AsyncSession,
    query_embedding: list[float],
    top_k: int = 10,
) -> list[SearchResult]:
    """Vektör benzerliğine göre madde ara."""
    query = sql_text("""
        SELECT id, law_number, law_name, article_number, title, text_clean,
               1 - (embedding <=> :query_vec::vector) AS score
        FROM law_articles
        ORDER BY embedding <=> :query_vec::vector
        LIMIT :top_k
    """)
    result = await session.execute(query, {
        "query_vec": str(query_embedding),
        "top_k": top_k,
    })
    return [
        SearchResult(
            article_id=row.id,
            law_number=row.law_number,
            law_name=row.law_name,
            article_number=row.article_number,
            title=row.title or "",
            text=row.text_clean,
            score=float(row.score),
            source="vector",
        )
        for row in result.fetchall()
    ]
