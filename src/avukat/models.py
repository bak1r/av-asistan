from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    """Bir kanun maddesi."""
    law_number: int           # 5237 (TCK) veya 5271 (CMK)
    law_name: str             # "Turk Ceza Kanunu"
    article_number: str       # "81", "142/1"
    text: str                 # Madde tam metni
    title: str = ""           # Madde basligi
    chapter: str = ""         # Bolum
    section: str = ""         # Kisim
    amendment_notes: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Arama sonucu."""
    article_id: int
    law_number: int
    law_name: str
    article_number: str
    title: str
    text: str
    score: float
    source: str  # "vector" | "bm25" | "hybrid"


@dataclass
class VerifiedSource:
    """Dogrulanmis kaynak."""
    index: int
    law_number: int
    law_name: str
    article_number: str
    title: str
    text_snippet: str


@dataclass
class RAGResponse:
    """RAG pipeline ciktisi."""
    question: str
    answer: str
    sources: list[VerifiedSource]
    confidence: float
    search_results: list[SearchResult]


@dataclass
class VoiceEvent:
    """WebSocket uzerinden gonderilen sesli asistan olaylari."""
    type: str       # transcript | tool_call | tool_result | status | error
    data: dict = field(default_factory=dict)


@dataclass
class MemoryFact:
    """Hafizadan cikan bir bilgi parcasi."""
    category: str
    key: str
    value: str
    confidence: float = 1.0
