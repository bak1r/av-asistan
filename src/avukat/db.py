from sqlalchemy import Column, Integer, String, Text, Index, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from pgvector.sqlalchemy import Vector

from avukat.config import Settings


class Base(DeclarativeBase):
    pass


class LawArticle(Base):
    __tablename__ = "law_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    law_number = Column(Integer, nullable=False)           # 5237 veya 5271
    law_name = Column(String(200), nullable=False)
    article_number = Column(String(20), nullable=False)
    title = Column(String(500), default="")
    chapter = Column(String(500), default="")
    section = Column(String(500), default="")
    text_original = Column(Text, nullable=False)            # Orijinal metin
    text_clean = Column(Text, nullable=False)               # Temizlenmiş metin
    text_search = Column(TSVECTOR)                          # Full-text arama
    embedding = Column(Vector(384), nullable=False)         # Vektör
    amendment_notes = Column(JSONB, default=[])
    metadata_ = Column("metadata", JSONB, default={})

    __table_args__ = (
        Index("idx_articles_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("idx_articles_text_search", "text_search", postgresql_using="gin"),
        Index("idx_articles_law_article", "law_number", "article_number", unique=True),
    )


# Veritabanı bağlantısı
_engine = None
_session_factory = None


def get_engine(settings: Settings | None = None):
    global _engine
    if _engine is None:
        if settings is None:
            settings = Settings()
        _engine = create_async_engine(settings.database_url, echo=settings.debug)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def init_db(settings: Settings | None = None):
    """Veritabanı tablolarını oluştur ve pgvector uzantısını etkinleştir."""
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(settings: Settings | None = None):
    """Tüm tabloları sil."""
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
