"""Veritabanını sıfırla: tabloları sil ve yeniden oluştur."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from avukat.config import Settings
from avukat.db import init_db, drop_db


async def main():
    settings = Settings()
    print(f"Veritabanı: {settings.database_url}")
    print("Tablolar siliniyor...")
    await drop_db(settings)
    print("Tablolar yeniden oluşturuluyor...")
    await init_db(settings)
    print("Veritabanı hazır.")


if __name__ == "__main__":
    asyncio.run(main())
