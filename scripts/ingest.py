"""TCK ve CMK maddelerini çekip veritabanına yükle."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from avukat.config import Settings
from avukat.ingestion.loader import load_all_laws


async def main():
    settings = Settings()
    print(f"Veritabanı: {settings.database_url}")
    print(f"Embedding modeli: {settings.embedding_model}")
    print()

    total = await load_all_laws(settings)

    if total > 0:
        print(f"\nBaşarılı! {total} madde yüklendi.")
        print("Şimdi 'docker compose up app' ile uygulamayı başlatabilirsiniz.")
    else:
        print("\nHiçbir madde yüklenemedi. API bağlantısını kontrol edin.")


if __name__ == "__main__":
    asyncio.run(main())
