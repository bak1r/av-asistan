"""PostgreSQL tabanli kullanici hafiza servisi."""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from avukat.db import MemoryEntry
from avukat.llm.base import BaseLLMClient
from avukat.memory.extractor import MemoryExtractor

logger = logging.getLogger(__name__)


class MemoryService:
    """Kullanici bilgilerini PostgreSQL'de saklar ve getirir."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: BaseLLMClient | None = None,
    ):
        self.session_factory = session_factory
        self.extractor = MemoryExtractor(llm) if llm else None

    async def get_memories(
        self,
        user_id: str,
        category: str | None = None,
    ) -> Sequence[MemoryEntry]:
        """Kullanicinin aktif hafiza kayitlarini getir."""
        async with self.session_factory() as session:
            query = select(MemoryEntry).where(
                MemoryEntry.user_id == user_id,
                MemoryEntry.is_active.is_(True),
            )
            if category:
                query = query.where(MemoryEntry.category == category)
            result = await session.execute(query.order_by(MemoryEntry.updated_at.desc()))
            return result.scalars().all()

    async def upsert(
        self,
        user_id: str,
        category: str,
        key: str,
        value: str,
        session_id: str | None = None,
    ) -> MemoryEntry:
        """Hafiza kaydi ekle veya guncelle."""
        async with self.session_factory() as session:
            existing = await session.execute(
                select(MemoryEntry).where(
                    MemoryEntry.user_id == user_id,
                    MemoryEntry.key == key,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.value = value
                row.category = category
                row.source_session_id = session_id
                row.is_active = True
            else:
                row = MemoryEntry(
                    user_id=user_id,
                    category=category,
                    key=key,
                    value=value,
                    source_session_id=session_id,
                )
                session.add(row)
            await session.commit()
            return row

    async def format_for_prompt(self, user_id: str, max_chars: int = 800) -> str:
        """Hafizayi sistem promptuna eklenecek formata donustur."""
        memories = await self.get_memories(user_id)
        if not memories:
            return ""

        lines = []
        total = 0
        for m in memories:
            line = f"- {m.key}: {m.value}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)

        if not lines:
            return ""
        return "KULLANICI HAFIZASI:\n" + "\n".join(lines)

    async def extract_and_store(
        self,
        user_id: str,
        conversation_text: str,
        session_id: str | None = None,
    ) -> list[dict]:
        """Konusmadan bilgi cikar ve hafizaya kaydet (2-asamali)."""
        if not self.extractor:
            return []

        # Asama 1: Hizli kontrol
        has_info = await self.extractor.has_memorable_content(conversation_text)
        if not has_info:
            return []

        # Asama 2: Tam cikarma
        facts = await self.extractor.extract(conversation_text)

        # Asama 3: Veritabanina yaz
        for fact in facts:
            await self.upsert(
                user_id=user_id,
                category=fact["category"],
                key=fact["key"],
                value=fact["value"],
                session_id=session_id,
            )

        logger.info(f"Extracted {len(facts)} memory facts for user {user_id}")
        return facts
