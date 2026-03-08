"""Kaynak doğrulama ve güven skoru."""
from __future__ import annotations

import re

from avukat.models import SearchResult, VerifiedSource


class CitationVerifier:
    """LLM yanıtındaki kaynak atıflarını doğrular."""

    def verify(
        self,
        answer: str,
        search_results: list[SearchResult],
    ) -> tuple[list[VerifiedSource], list[int], float]:
        """Yanıttaki [Kaynak N] atıflarını doğrula.

        Returns:
            (verified_sources, invalid_indices, confidence_score)
        """
        # [Kaynak N] referanslarını çıkar
        cited_indices = set(int(m) for m in re.findall(r"\[Kaynak (\d+)\]", answer))

        valid_range = set(range(1, len(search_results) + 1))
        invalid = sorted(cited_indices - valid_range)
        valid = sorted(cited_indices & valid_range)

        # Doğrulanmış kaynakları oluştur
        sources = []
        for idx in valid:
            r = search_results[idx - 1]
            law_label = "TCK" if r.law_number == 5237 else "CMK"
            sources.append(VerifiedSource(
                index=idx,
                law_number=r.law_number,
                law_name=r.law_name,
                article_number=r.article_number,
                title=r.title,
                text_snippet=r.text[:300] if r.text else "",
            ))

        # Güven skoru hesapla
        confidence = self._compute_confidence(answer, len(valid), len(invalid), len(search_results))

        return sources, invalid, confidence

    def _compute_confidence(
        self, answer: str, cited_count: int, invalid_count: int, total_results: int
    ) -> float:
        """Basit güven skoru: 0.0 - 1.0"""
        score = 1.0

        # Atıf yoksa puan düş
        if cited_count == 0:
            score -= 0.4

        # Geçersiz atıflar varsa puan düş
        score -= invalid_count * 0.2

        # Belirsizlik ifadeleri varsa puan düş
        hedging = [
            "emin değilim", "bilinmiyor", "net değildir", "olabilir",
            "kesin olmamakla birlikte", "yeterli bilgi bulunamadı",
        ]
        for phrase in hedging:
            if phrase in answer.lower():
                score -= 0.1

        return max(0.0, min(1.0, score))
