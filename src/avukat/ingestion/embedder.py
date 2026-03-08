"""Madde metinlerinden vektör embedding üretimi."""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer
from rich.console import Console

from avukat.models import Article

console = Console()


class ArticleEmbedder:
    """sentence-transformers ile madde embedding üretici."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        console.print(f"[bold]Embedding modeli yukleniyor: {model_name}[/]")
        self.model = SentenceTransformer(model_name, device="cpu")
        self.dimension = self.model.get_sentence_embedding_dimension()
        console.print(f"  Boyut: {self.dimension}")

    def _prepare_text(self, article: Article) -> str:
        """Maddeyi embedding için hazırla: metadata prefix + temiz metin."""
        law_label = "TCK" if article.law_number == 5237 else "CMK"
        prefix = f"[{law_label} Madde {article.article_number}"
        if article.title:
            prefix += f" - {article.title}"
        prefix += "]"
        return f"{prefix} {article.text}"

    def embed_article(self, article: Article) -> np.ndarray:
        """Tek bir maddenin embedding'ini üret."""
        text = self._prepare_text(article)
        return self.model.encode(text, normalize_embeddings=True)

    def embed_query(self, query: str) -> np.ndarray:
        """Kullanıcı sorgusunun embedding'ini üret."""
        return self.model.encode(query, normalize_embeddings=True)

    def embed_batch(self, articles: list[Article], batch_size: int = 32) -> list[np.ndarray]:
        """Toplu embedding üretimi."""
        texts = [self._prepare_text(a) for a in articles]
        console.print(f"[bold]{len(texts)} madde için embedding üretiliyor...[/]")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return list(embeddings)
