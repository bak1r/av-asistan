"""Bedesten API üzerinden TCK/CMK maddelerini çekme."""
from __future__ import annotations

import base64
import asyncio
import httpx
from rich.console import Console

console = Console()

BASE_URL = "https://bedesten.adalet.gov.tr/mevzuat"
HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "AdaletApplicationName": "UyapMevzuat",
    "Origin": "https://mevzuat.adalet.gov.tr",
    "Referer": "https://mevzuat.adalet.gov.tr/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
}

# Çekilecek kanunlar
LAWS = {
    5237: "Türk Ceza Kanunu",
    5271: "Ceza Muhakemesi Kanunu",
}


def _wrap(data: dict) -> dict:
    return {"data": data, "applicationName": "UyapMevzuat"}


def _wrap_paging(data: dict) -> dict:
    return {"data": data, "applicationName": "UyapMevzuat", "paging": True}


def _check_response(body: dict) -> dict:
    """API yanıtını kontrol et, hata varsa exception fırlat."""
    meta = body.get("metadata", {})
    if meta.get("FMTY") != "SUCCESS":
        raise RuntimeError(f"API hatası: {meta.get('FMTE', 'Bilinmeyen hata')}")
    return body["data"]


class BedestinFetcher:
    """Bedesten API ile mevzuat verisi çeker."""

    def __init__(self, timeout: float = 60.0):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=HEADERS,
            timeout=timeout,
        )

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def search_law(self, law_number: int) -> dict | None:
        """Kanun numarasıyla arama yap, mevzuat bilgisini döndür."""
        payload = {
            "pageSize": 5,
            "pageNumber": 1,
            "sortFields": ["RESMI_GAZETE_TARIHI"],
            "sortDirection": "desc",
            "mevzuatNo": str(law_number),
            "mevzuatTurList": ["KANUN"],
        }
        resp = await self.client.post("/searchDocuments", json=_wrap_paging(payload))
        resp.raise_for_status()
        data = _check_response(resp.json())

        results = data.get("mevzuatList", [])
        if not results:
            return None
        return results[0]

    async def get_article_tree(self, mevzuat_id: str) -> list[dict]:
        """Kanunun madde ağacını çek."""
        resp = await self.client.post(
            "/mevzuatMaddeTree",
            json=_wrap({"mevzuatId": mevzuat_id}),
        )
        resp.raise_for_status()
        data = _check_response(resp.json())
        return data.get("children", [])

    async def get_article_content(self, madde_id: str) -> str:
        """Tek bir maddenin HTML içeriğini çek."""
        resp = await self.client.post(
            "/getDocumentContent",
            json=_wrap({"documentType": "MADDE", "id": madde_id}),
        )
        resp.raise_for_status()
        data = _check_response(resp.json())
        raw = data.get("content", "")
        if not raw:
            return ""
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    async def get_full_content(self, mevzuat_id: str) -> str:
        """Kanunun tam metnini çek (fallback için)."""
        resp = await self.client.post(
            "/getDocumentContent",
            json=_wrap({"documentType": "MEVZUAT", "id": mevzuat_id}),
        )
        resp.raise_for_status()
        data = _check_response(resp.json())
        raw = data.get("content", "")
        if not raw:
            return ""
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    def flatten_tree(self, nodes: list[dict], parent_chapter: str = "", parent_section: str = "") -> list[dict]:
        """Madde ağacını düz listeye çevir, bölüm/kısım bilgisini ekle."""
        flat = []
        for node in nodes:
            madde_id = node.get("maddeId")
            madde_no = node.get("maddeNo", "")
            title = node.get("maddeBaslik", "")
            section_title = node.get("title", "")

            # Bölüm/kısım başlığı varsa güncelle
            current_chapter = parent_chapter
            current_section = parent_section
            if section_title:
                # "Birinci Bölüm", "İkinci Kısım" gibi yapısal başlıklar
                lower = section_title.lower()
                if "kısım" in lower or "kisim" in lower:
                    current_section = section_title
                elif "bölüm" in lower or "bolum" in lower:
                    current_chapter = section_title
                else:
                    current_chapter = section_title

            # Bu düğüm bir madde mi?
            if madde_id and madde_no:
                flat.append({
                    "madde_id": madde_id,
                    "madde_no": madde_no,
                    "title": title,
                    "chapter": current_chapter,
                    "section": current_section,
                    "gerekce_id": node.get("gerekceId"),
                })

            # Alt düğümleri dolaş
            children = node.get("children", [])
            if children:
                flat.extend(self.flatten_tree(children, current_chapter, current_section))

        return flat

    async def fetch_law_articles(self, law_number: int) -> list[dict]:
        """Bir kanunun tüm maddelerini çek.

        Returns:
            [{madde_no, title, chapter, section, html_content}, ...]
        """
        law_name = LAWS.get(law_number, f"Kanun {law_number}")
        console.print(f"\n[bold blue]📖 {law_name} ({law_number}) çekiliyor...[/]")

        # 1. Kanunu bul
        law_info = await self.search_law(law_number)
        if not law_info:
            console.print(f"[red]❌ Kanun {law_number} bulunamadı![/]")
            return []

        mevzuat_id = law_info["mevzuatId"]
        console.print(f"  Mevzuat ID: {mevzuat_id}")

        # 2. Madde ağacını çek
        tree = await self.get_article_tree(mevzuat_id)
        flat_articles = self.flatten_tree(tree)
        console.print(f"  {len(flat_articles)} madde bulundu")

        # 3. Her maddenin içeriğini çek
        articles = []
        for i, article_info in enumerate(flat_articles):
            html = await self.get_article_content(article_info["madde_id"])
            articles.append({
                "law_number": law_number,
                "law_name": law_name,
                "madde_no": article_info["madde_no"],
                "title": article_info["title"],
                "chapter": article_info["chapter"],
                "section": article_info["section"],
                "html_content": html,
            })

            if (i + 1) % 50 == 0:
                console.print(f"  {i + 1}/{len(flat_articles)} madde çekildi...")

            # Rate limiting: API'yi yormamak için kısa bekle
            await asyncio.sleep(0.1)

        console.print(f"  [green]✓ {len(articles)} madde başarıyla çekildi[/]")
        return articles
