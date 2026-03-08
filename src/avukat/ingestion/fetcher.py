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
        """Bir kanunun tum maddelerini cek.

        Strateji: Tam metni tek seferde cek + madde agacindan metadata al.
        Boylece 345 API cagrisi yerine sadece 3 cagri yapiyoruz.

        Returns:
            [{madde_no, title, chapter, section, html_content}, ...]
        """
        import re
        from bs4 import BeautifulSoup

        law_name = LAWS.get(law_number, f"Kanun {law_number}")
        console.print(f"\n[bold blue]{law_name} ({law_number}) cekiliyor...[/]")

        # 1. Kanunu bul
        law_info = await self.search_law(law_number)
        if not law_info:
            console.print(f"[red]HATA: Kanun {law_number} bulunamadi![/]")
            return []

        mevzuat_id = law_info["mevzuatId"]
        console.print(f"  Mevzuat ID: {mevzuat_id}")

        # 2. Madde agacini cek (metadata: baslik, bolum, kisim)
        tree = await self.get_article_tree(mevzuat_id)
        flat_articles = self.flatten_tree(tree)
        console.print(f"  {len(flat_articles)} madde bulundu (agac)")

        # 3. Tam metni tek seferde cek (1 API cagrisi)
        console.print("  Tam metin cekiliyor...")
        full_html = await self.get_full_content(mevzuat_id)
        console.print(f"  Tam metin: {len(full_html)} karakter")

        # 4. HTML'den temiz metin cikar
        soup = BeautifulSoup(full_html, "lxml")
        full_text = soup.get_text(separator="\n")

        # 5. Madde metinlerini regex ile ayir
        # "Madde 1 -" veya "Madde 81 -" vb. pattern
        splits = re.split(r"((?:Madde|MADDE)\s+(\d+)\s*[\-\u2013]?)", full_text)

        article_texts: dict[str, str] = {}
        i = 0
        while i < len(splits):
            # Regex gruplari: [onceki_metin, "Madde N -", "N", sonraki_metin, ...]
            if i + 2 < len(splits) and splits[i + 2] and splits[i + 2].isdigit():
                madde_no = splits[i + 2]
                header = splits[i + 1]  # "Madde N -"
                # Sonraki bolume kadar olan metin
                content = splits[i + 3] if i + 3 < len(splits) else ""
                article_texts[madde_no] = (header + content).strip()
                i += 3
            else:
                i += 1

        # 6. Agac metadatasiyla eslestir
        articles = []
        matched = 0
        for article_info in flat_articles:
            madde_no = str(article_info["madde_no"]).strip()
            text = article_texts.get(madde_no, "")
            if text:
                matched += 1
            articles.append({
                "law_number": law_number,
                "law_name": law_name,
                "madde_no": madde_no,
                "title": article_info["title"],
                "chapter": article_info["chapter"],
                "section": article_info["section"],
                "html_content": text,
            })

        console.print(f"  [green]{matched}/{len(flat_articles)} madde eslesti[/]")
        return articles
