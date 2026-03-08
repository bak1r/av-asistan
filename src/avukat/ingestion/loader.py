"""Veri yükleme orkestratörü: fetch → parse → embed → store."""
from __future__ import annotations

from sqlalchemy import text as sql_text
from rich.console import Console

from avukat.config import Settings
from avukat.db import get_session_factory, LawArticle, init_db
from avukat.ingestion.fetcher import BedestinFetcher, LAWS
from avukat.ingestion.parser import parse_articles
from avukat.ingestion.embedder import ArticleEmbedder

console = Console()


async def load_law(
    law_number: int,
    settings: Settings | None = None,
    embedder: ArticleEmbedder | None = None,
) -> int:
    """Bir kanunu çek, ayrıştır, embedle ve veritabanına yaz.

    Returns:
        Yüklenen madde sayısı.
    """
    if settings is None:
        settings = Settings()

    # Veritabanını hazırla
    await init_db(settings)
    session_factory = get_session_factory(settings)

    # Embedder oluştur
    if embedder is None:
        embedder = ArticleEmbedder(settings.embedding_model)

    # 1. Fetch: API'den maddeleri çek
    async with BedestinFetcher() as fetcher:
        raw_articles = await fetcher.fetch_law_articles(law_number)

    if not raw_articles:
        console.print(f"[red]Kanun {law_number} için madde bulunamadı![/]")
        return 0

    # 2. Parse: HTML'den yapısal Article nesnelerine dönüştür
    articles = parse_articles(raw_articles)
    console.print(f"[bold]{len(articles)} madde ayrıştırıldı[/]")

    # 3. Embed: Vektör üret
    embeddings = embedder.embed_batch(articles)

    # 4. Store: Veritabanına yaz
    async with session_factory() as session:
        # Önce bu kanunun mevcut maddelerini sil (güncelleme için)
        await session.execute(
            sql_text("DELETE FROM law_articles WHERE law_number = :law_no"),
            {"law_no": law_number},
        )

        count = 0
        for article, embedding in zip(articles, embeddings):
            row = LawArticle(
                law_number=article.law_number,
                law_name=article.law_name,
                article_number=article.article_number,
                title=article.title,
                chapter=article.chapter,
                section=article.section,
                text_original=article.text,
                text_clean=article.text,
                embedding=embedding.tolist(),
                amendment_notes=article.amendment_notes,
            )
            session.add(row)
            count += 1

        await session.commit()

        # tsvector güncelle (trigger yoksa manuel)
        await session.execute(sql_text(
            "UPDATE law_articles SET text_search = to_tsvector('simple', text_clean) "
            "WHERE law_number = :law_no"
        ), {"law_no": law_number})
        await session.commit()

    console.print(f"[green bold]✓ {count} madde veritabanına yüklendi[/]")
    return count


async def load_all_laws(settings: Settings | None = None) -> int:
    """TCK ve CMK'yı yükle."""
    if settings is None:
        settings = Settings()

    embedder = ArticleEmbedder(settings.embedding_model)
    total = 0

    for law_number in LAWS:
        count = await load_law(law_number, settings, embedder)
        total += count

    console.print(f"\n[green bold]═══ Toplam {total} madde yüklendi ═══[/]")
    return total
