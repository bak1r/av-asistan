from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    """Bir kanun maddesi."""
    law_number: int           # 5237 (TCK) veya 5271 (CMK)
    law_name: str             # "Türk Ceza Kanunu"
    article_number: str       # "81", "142/1"
    text: str                 # Madde tam metni
    title: str = ""           # Madde başlığı
    chapter: str = ""         # Bölüm
    section: str = ""         # Kısım
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
    """Doğrulanmış kaynak."""
    index: int
    law_number: int
    law_name: str
    article_number: str
    title: str
    text_snippet: str


@dataclass
class RAGResponse:
    """RAG pipeline çıktısı."""
    question: str
    answer: str
    sources: list[VerifiedSource]
    confidence: float
    search_results: list[SearchResult]
