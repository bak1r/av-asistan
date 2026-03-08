"""PostgreSQL tsvector full-text araması."""
from __future__ import annotations

import re

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from avukat.models import SearchResult


def _build_or_tsquery(query: str) -> str:
    """Kullanıcı sorgusundan OR tabanlı tsquery oluştur.

    plainto_tsquery AND kullanır, Türkçe stemming olmadığı için
    çekim ekli kelimeler eşleşmez. Bunun yerine kelimeleri OR ile
    birleştirip prefix matching (:*) kullanıyoruz.
    """
    words = re.findall(r"\w+", query.lower())
    # Stop words (Türkçe)
    stop = {"bir", "ve", "veya", "ile", "de", "da", "mi", "mu", "mı",
            "ne", "nasıl", "nedir", "nelerdir", "neler", "hangi", "kaç",
            "bu", "şu", "o", "için", "olan", "olarak", "gibi", "ise"}
    words = [w for w in words if w not in stop and len(w) > 1]
    if not words:
        return query  # Fallback: orijinal sorgu
    # Prefix matching ile OR: "tutuklama:* | kosul:*"
    return " | ".join(f"{w}:*" for w in words)


async def bm25_search(
    session: AsyncSession,
    query: str,
    top_k: int = 10,
) -> list[SearchResult]:
    """Full-text arama (BM25 benzeri ts_rank)."""
    tsquery_str = _build_or_tsquery(query)
    sql = sql_text("""
        SELECT id, law_number, law_name, article_number, title, text_clean,
               ts_rank(text_search, to_tsquery('simple', :tsquery)) AS score
        FROM law_articles
        WHERE text_search @@ to_tsquery('simple', :tsquery)
        ORDER BY score DESC
        LIMIT :top_k
    """)
    result = await session.execute(sql, {"tsquery": tsquery_str, "top_k": top_k})
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
