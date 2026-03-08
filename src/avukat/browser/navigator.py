"""UYAP sayfa objeleri — stub implementasyon.

Gelecekte UYAP (Ulusal Yargi Agi Bilisim Sistemi) entegrasyonu icin
sayfa navigasyon ve form doldurma islemleri burada tanimlanacak.
"""
from __future__ import annotations

import logging
from typing import Any

from avukat.browser.manager import BrowserManager

logger = logging.getLogger(__name__)

# UYAP URL'leri (gelecek icin placeholder)
UYAP_BASE_URL = "https://uyap.gov.tr"
UYAP_PORTAL_URL = f"{UYAP_BASE_URL}/avukat"


class UYAPNavigator:
    """UYAP portal navigasyonu.

    STUB: Gercek UYAP entegrasyonu icin e-imza / mobil imza
    gereklidir. Su an sadece arayuz tanimli.
    """

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def login(self, tc_no: str, password: str) -> dict[str, Any]:
        """UYAP giris (stub)."""
        logger.warning("UYAP login is a stub — not implemented yet")
        return {
            "success": False,
            "message": "UYAP entegrasyonu henuz aktif degil. "
            "e-Imza/mobil imza destegi gereklidir.",
        }

    async def search_case(self, case_number: str) -> dict[str, Any]:
        """Dava sorgulama (stub)."""
        logger.warning("UYAP case search is a stub — not implemented yet")
        return {
            "success": False,
            "message": "Dava sorgulama henuz aktif degil.",
        }

    async def search_person(self, tc_no: str) -> dict[str, Any]:
        """Kisi sorgulama (stub)."""
        logger.warning("UYAP person search is a stub — not implemented yet")
        return {
            "success": False,
            "message": "Kisi sorgulama henuz aktif degil.",
        }
