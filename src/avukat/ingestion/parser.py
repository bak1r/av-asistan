"""HTML madde içeriklerini yapısal Article nesnelerine dönüştürme."""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

from avukat.models import Article


def clean_html(html: str) -> str:
    """HTML'den temiz metin çıkar."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")

    # Script ve style etiketlerini kaldır
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Çoklu boşlukları temizle
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


def extract_amendment_notes(html: str) -> list[str]:
    """HTML'den değişiklik notlarını çıkar."""
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    notes = []

    # Değişiklik notları genellikle parantez veya dipnot olarak gelir
    for footnote in soup.find_all(["sup", "span"], class_=re.compile(r"(footnote|degisiklik|ek|iptal)", re.I)):
        text = footnote.get_text(strip=True)
        if text:
            notes.append(text)

    # Metin içindeki değişiklik referanslarını da yakala
    text = soup.get_text()
    # "(Ek: 18/6/2014-6545/58 md.)" formatındaki notlar
    amendment_pattern = r"\((?:Ek|Değişik|Mülga|İptal)[^)]+\)"
    for match in re.findall(amendment_pattern, text):
        if match not in notes:
            notes.append(match)

    return notes


def parse_article(raw: dict) -> Article:
    """Ham API verisini Article nesnesine dönüştür.

    Args:
        raw: fetcher'dan gelen dict:
            {law_number, law_name, madde_no, title, chapter, section, html_content}
    """
    html = raw.get("html_content", "")
    text_clean = clean_html(html)
    amendment_notes = extract_amendment_notes(html)

    return Article(
        law_number=raw["law_number"],
        law_name=raw["law_name"],
        article_number=str(raw["madde_no"]),
        text=text_clean,
        title=raw.get("title", ""),
        chapter=raw.get("chapter", ""),
        section=raw.get("section", ""),
        amendment_notes=amendment_notes,
    )


def parse_articles(raw_list: list[dict]) -> list[Article]:
    """Ham madde listesini Article listesine dönüştür."""
    articles = []
    for raw in raw_list:
        article = parse_article(raw)
        # Boş maddeleri atla
        if article.text.strip():
            articles.append(article)
    return articles
