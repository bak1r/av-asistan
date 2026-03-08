"""Gemini Live API tool declarations — sesli asistan araclari."""
from __future__ import annotations

# Gemini function-calling tool tanimlari

LEGAL_SEARCH_TOOL = {
    "name": "hukuki_soru_sor",
    "description": (
        "Turk Ceza Kanunu (TCK, 5237 sayili) ve Ceza Muhakemesi Kanunu (CMK, 5271 sayili) "
        "hakkinda hukuki soru sorar. Veritabanindaki 677 kanun maddesinde arama yapar "
        "ve ilgili maddeleri bularak yanitlar. "
        "Kullanicinin herhangi bir hukuki sorusu oldugunda HER ZAMAN bu araci kullan. "
        "Kendi bilginle dogrudan yanitlama, once bu araci cagir."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "soru": {
                "type": "string",
                "description": (
                    "Kullanicinin hukuki sorusu, Turkce olarak. "
                    "Ornekler: 'Hirsizlik sucunun cezasi nedir?', "
                    "'Tutuklama kosullari nelerdir?', "
                    "'Mesfru mudafaa nedir?'"
                ),
            }
        },
        "required": ["soru"],
    },
}

ARTICLE_LOOKUP_TOOL = {
    "name": "madde_ara",
    "description": (
        "Belirli bir kanun maddesini numara ile dogrudan arar ve tam metnini getirir. "
        "Kullanici belirli bir madde numarasi istediginde bu araci kullan. "
        "Ornegin 'TCK 141 ne diyor?', 'CMK 100. maddeyi oku' gibi."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kanun": {
                "type": "string",
                "enum": ["TCK", "CMK"],
                "description": "Kanun kodu: TCK (Turk Ceza Kanunu) veya CMK (Ceza Muhakemesi Kanunu)",
            },
            "madde_no": {
                "type": "string",
                "description": "Madde numarasi, ornegin '81', '142', '100'",
            },
        },
        "required": ["kanun", "madde_no"],
    },
}

MEMORY_RECALL_TOOL = {
    "name": "hafiza_hatirla",
    "description": (
        "Kullanici hakkinda daha once ogrenilen bilgileri hatirla. "
        "Kullanicinin adi, meslegi, calisma alani, devam eden davalari gibi "
        "bilgileri getirir. Konusma basinda veya kullanici kisisel bilgiye "
        "referans verdiginde kullan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kategori": {
                "type": "string",
                "enum": ["identity", "preferences", "case_context", "notes"],
                "description": (
                    "Hatirlanacak bilgi kategorisi. "
                    "identity: isim/meslek/sehir, "
                    "preferences: tercihler, "
                    "case_context: aktif davalar, "
                    "notes: diger notlar. "
                    "Bos birakilirsa tum kategoriler gelir."
                ),
            }
        },
        "required": [],
    },
}

ALL_TOOLS = [LEGAL_SEARCH_TOOL, ARTICLE_LOOKUP_TOOL, MEMORY_RECALL_TOOL]
