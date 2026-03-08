"""PostgreSQL tsvector full-text araması."""
from __future__ import annotations

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from avukat.models import SearchResult


async def bm25_search(
    session: AsyncSession,
    query: str,
    top_k: int = 10,
) -> list[SearchResult]:
    """Full-text arama (BM25 benzeri ts_rank)."""
    sql = sql_text("""
        SELECT id, law_number, law_name, article_number, title, text_clean,
               ts_rank(text_search, plainto_tsquery('simple', :query)) AS score
        FROM law_articles
        WHERE text_search @@ plainto_tsquery('simple', :query)
        ORDER BY score DESC
        LIMIT :top_k
    """)
    result = await session.execute(sql, {"query": query, "top_k": top_k})
    return [
        SearchResult(
            article_id=row.id,
            law_number=row.law_number,
            law_name=row.law_name,
            article_number=row.article_number,
            title=row.title or "",
            text=row.text_clean,
            score=float(row.score),
            source="bm25",
        )
        for row in result.fetchall()
    ]
