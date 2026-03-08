"""2-asamali hafiza bilgi cikartma (Mark-XXX pattern)."""
from __future__ import annotations

import json
import logging

from avukat.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_DETECT_PROMPT = """Asagidaki konusma metninde kullanici hakkinda hatirlanabilecek kisisel bilgi var mi?
Sadece YES veya NO yaz.

Konusma:
{text}"""

_EXTRACT_PROMPT = """Asagidaki konusma metninden kullanici hakkinda hatirlamamiz gereken bilgileri cikar.
JSON dizisi olarak don. Her eleman: {{"category": "...", "key": "...", "value": "..."}}

Kategoriler:
- identity: isim, meslek, sehir, yas
- preferences: tercihler, calisma alani
- case_context: aktif dava bilgileri, muvekiller
- notes: diger onemli bilgiler

Sadece JSON dizisi don, baska bir sey yazma. Bilgi yoksa bos dizi don: []

Konusma:
{text}"""


class MemoryExtractor:
    """LLM ile konusmadan kullanici bilgisi cikarir."""

    def __init__(self, llm: BaseLLMClient):
        self.llm = llm

    async def has_memorable_content(self, text: str) -> bool:
        """Hizli kontrol: konusmada hatirlanacak bilgi var mi?"""
        try:
            response = await self.llm.generate(_DETECT_PROMPT.format(text=text[:500]))
            return "YES" in response.upper()
        except Exception as e:
            logger.warning(f"Memory detection failed: {e}")
            return False

    async def extract(self, text: str) -> list[dict]:
        """Konusmadan yapisal bilgi cikar."""
        try:
            response = await self.llm.generate(_EXTRACT_PROMPT.format(text=text[:2000]))
            # JSON'u temizle
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0]
            facts = json.loads(response)
            if not isinstance(facts, list):
                return []
            # Dogrulama
            valid = []
            for f in facts:
                if all(k in f for k in ("category", "key", "value")):
                    valid.append({
                        "category": str(f["category"])[:50],
                        "key": str(f["key"])[:200],
                        "value": str(f["value"])[:300],
                    })
            return valid
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Memory extraction failed: {e}")
            return []
