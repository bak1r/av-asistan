from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, Index, text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from pgvector.sqlalchemy import Vector

from avukat.config import Settings


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# Phase 1: Kanun maddeleri
# ──────────────────────────────────────────────

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
    text_clean = Column(Text, nullable=False)               # Temizlenmis metin
    text_search = Column(TSVECTOR)                          # Full-text arama
    embedding = Column(Vector(384), nullable=False)         # Vektor
    amendment_notes = Column(JSONB, default=[])
    metadata_ = Column("metadata", JSONB, default={})

    __table_args__ = (
        Index("idx_articles_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("idx_articles_text_search", "text_search", postgresql_using="gin"),
        Index("idx_articles_law_article", "law_number", "article_number", unique=True),
    )


# ──────────────────────────────────────────────
# Phase 2: Sesli asistan + hafiza
# ──────────────────────────────────────────────

class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    id = Column(String(36), primary_key=True)               # UUID
    user_id = Column(String(100), default="anonymous")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    total_turns = Column(Integer, default=0)
    metadata_ = Column("metadata", JSONB, default={})


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("voice_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)               # user | assistant | tool_call | tool_result
    content = Column(Text, nullable=False)
    tool_name = Column(String(100), nullable=True)
    tool_args = Column(JSONB, nullable=True)
    tool_result = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    audio_duration_ms = Column(Integer, nullable=True)


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)           # identity | preferences | case_context | notes
    key = Column(String(200), nullable=False)
    value = Column(Text, nullable=False)
    confidence = Column(Float, default=1.0)
    source_session_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_memory_user_category", "user_id", "category"),
        Index("idx_memory_user_key", "user_id", "key", unique=True),
    )


# ──────────────────────────────────────────────
# Veritabani baglantisi
# ──────────────────────────────────────────────

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
    """Veritabani tablolarini olustur ve pgvector uzantisini etkinlestir."""
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(settings: Settings | None = None):
    """Tum tablolari sil."""
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
