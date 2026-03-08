"""Sesli asistan oturum yoneticisi — Gemini Live API ile bidirectional audio."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from avukat.config import Settings
from avukat.ingestion.embedder import ArticleEmbedder
from avukat.llm.base import BaseLLMClient
from avukat.memory.service import MemoryService
from avukat.rag.pipeline import RAGPipeline
from avukat.voice.prompts import VOICE_SYSTEM_PROMPT
from avukat.voice.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


class VoiceSessionManager:
    """Tek bir sesli konusma oturumunu yonetir.

    Gemini Live API (v1beta) ile bidirectional audio streaming.
    connect() async context manager olarak kullanilir.
    """

    def __init__(
        self,
        settings: Settings,
        embedder: ArticleEmbedder,
        text_llm: BaseLLMClient,
        session_factory: async_sessionmaker[AsyncSession],
        memory_service: MemoryService | None = None,
        user_id: str = "anonymous",
    ):
        self.settings = settings
        self.embedder = embedder
        self.text_llm = text_llm
        self.session_factory = session_factory
        self.memory_service = memory_service
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())

        # Async kuyruklar
        self._audio_in: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)
        self._audio_out: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)
        self._events: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=100)

        self._gemini_session = None
        self._gemini_ctx = None  # async context manager
        self._running = False
        self._turn_count = 0
        self._conversation_text: list[str] = []

    async def start(self):
        """Gemini Live API'ye baglan ve streaming'i baslat."""
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=self.settings.google_api_key,
            http_options={"api_version": "v1beta"},
        )

        # Hafizayi prompt'a ekle
        system_prompt = VOICE_SYSTEM_PROMPT
        if self.memory_service:
            memory_context = await self.memory_service.format_for_prompt(self.user_id)
            if memory_context:
                system_prompt = f"{system_prompt}\n\n{memory_context}"

        # Tool tanimlari
        tool_declarations = [{"function_declarations": ALL_TOOLS}]

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            tools=tool_declarations,
        )

        # Yeni API: connect() async context manager dondurur
        self._gemini_ctx = client.aio.live.connect(
            model=f"models/{self.settings.gemini_live_model}",
            config=config,
        )
        self._gemini_session = await self._gemini_ctx.__aenter__()
        self._running = True

        await self._events.put({"type": "status", "state": "connected"})
        logger.info(f"Voice session {self.session_id} started for user {self.user_id}")

    async def run(self):
        """Ana dongu: Gemini'ye audio gonder ve yanit al."""
        tasks = [
            asyncio.create_task(self._send_audio_to_gemini()),
            asyncio.create_task(self._receive_from_gemini()),
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Voice session error: {e}")
            await self._events.put({"type": "error", "message": str(e)})
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    async def stop(self):
        """Oturumu kapat."""
        self._running = False
        # Kuyruklara None gonder (sentinel) tum task'leri durdur
        await self._audio_in.put(None)
        await self._audio_out.put(None)
        await self._events.put(None)

        if self._gemini_ctx:
            try:
                await self._gemini_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._gemini_session = None
            self._gemini_ctx = None

        # Hafiza cikarimi yap (her oturum sonunda)
        if self.memory_service and self._conversation_text:
            try:
                full_text = "\n".join(self._conversation_text)
                await self.memory_service.extract_and_store(
                    self.user_id, full_text, self.session_id
                )
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")

        logger.info(f"Voice session {self.session_id} stopped")

    async def feed_audio(self, chunk: bytes):
        """WebSocket'ten gelen PCM audio verisini kuyruga ekle."""
        if self._running:
            await self._audio_in.put(chunk)

    async def output_audio_stream(self):
        """Gemini'den gelen audio chunk'larini yield et."""
        while self._running:
            chunk = await self._audio_out.get()
            if chunk is None:
                break
            yield chunk

    async def event_stream(self):
        """JSON event'lerini yield et (transcript, tool_call, status)."""
        while self._running:
            event = await self._events.get()
            if event is None:
                break
            yield event

    # --- Internal async tasks ---

    async def _send_audio_to_gemini(self):
        """Audio kuyrugunu Gemini'ye realtime_input olarak gonder."""
        from google.genai import types

        while self._running:
            chunk = await self._audio_in.get()
            if chunk is None:
                break
            try:
                await self._gemini_session.send_realtime_input(
                    media=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm",
                    )
                )
            except Exception as e:
                logger.warning(f"Send audio error: {e}")

    async def _receive_from_gemini(self):
        """Gemini'den gelen yanitlari isle: audio + tool call + transcript."""
        from google.genai import types

        try:
            async for response in self._gemini_session.receive():
                if not self._running:
                    break

                # Audio yanit
                server_content = getattr(response, "server_content", None)
                if server_content:
                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn:
                        for part in model_turn.parts:
                            if hasattr(part, "inline_data") and part.inline_data:
                                await self._audio_out.put(part.inline_data.data)
                            if hasattr(part, "text") and part.text:
                                self._conversation_text.append(f"AI: {part.text}")
                                await self._events.put({
                                    "type": "transcript",
                                    "role": "assistant",
                                    "text": part.text,
                                })

                # Tool call
                tool_call = getattr(response, "tool_call", None)
                if tool_call:
                    for fc in tool_call.function_calls:
                        await self._events.put({
                            "type": "tool_call",
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        })

                        result = await self._dispatch_tool(
                            fc.name, dict(fc.args) if fc.args else {}
                        )
                        self._turn_count += 1

                        await self._events.put({
                            "type": "tool_result",
                            "name": fc.name,
                            "result": result,
                        })

                        # Sonucu Gemini'ye gonder (yeni API — id gerekli)
                        await self._gemini_session.send_tool_response(
                            function_responses=[types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response=result,
                            )]
                        )
        except Exception as e:
            if self._running:
                logger.error(f"Receive error: {e}")
                await self._events.put({"type": "error", "message": str(e)})

    async def _dispatch_tool(self, tool_name: str, args: dict) -> dict:
        """Arac cagrisini ilgili fonksiyona yonlendir."""
        logger.info(f"Tool call: {tool_name}({args})")

        if tool_name == "hukuki_soru_sor":
            return await self._tool_legal_search(args.get("soru", ""))
        elif tool_name == "madde_ara":
            return await self._tool_article_lookup(
                args.get("kanun", "TCK"),
                args.get("madde_no", ""),
            )
        elif tool_name == "hafiza_hatirla":
            return await self._tool_memory_recall(args.get("kategori"))
        else:
            return {"hata": f"Bilinmeyen arac: {tool_name}"}

    async def _tool_legal_search(self, question: str) -> dict:
        """Hukuki soru-cevap — mevcut RAG pipeline'i kullanir."""
        try:
            pipeline = RAGPipeline(
                embedder=self.embedder,
                llm=self.text_llm,
                settings=self.settings,
            )
            async with self.session_factory() as session:
                rag_response = await pipeline.answer(question, session)

            self._conversation_text.append(f"User (soru): {question}")

            return {
                "yanit": rag_response.answer,
                "kaynaklar": [
                    {
                        "kanun": "TCK" if s.law_number == 5237 else "CMK",
                        "madde": s.article_number,
                        "baslik": s.title,
                    }
                    for s in rag_response.sources
                ],
                "guven": rag_response.confidence,
            }
        except Exception as e:
            logger.error(f"Legal search error: {e}")
            return {"hata": f"Arama hatasi: {str(e)}"}

    async def _tool_article_lookup(self, kanun: str, madde_no: str) -> dict:
        """Dogrudan madde arama."""
        try:
            law_number = 5237 if kanun.upper() == "TCK" else 5271
            async with self.session_factory() as session:
                result = await session.execute(
                    sql_text(
                        "SELECT article_number, title, text_clean FROM law_articles "
                        "WHERE law_number = :ln AND article_number = :an"
                    ),
                    {"ln": law_number, "an": madde_no},
                )
                row = result.fetchone()
                if row:
                    return {
                        "madde": row.article_number,
                        "baslik": row.title,
                        "metin": row.text_clean[:2000],
                    }
                return {"hata": f"{kanun} Madde {madde_no} bulunamadi"}
        except Exception as e:
            return {"hata": str(e)}

    async def _tool_memory_recall(self, category: str | None) -> dict:
        """Kullanici hafizasini getir."""
        if not self.memory_service:
            return {"bilgi": "Hafiza servisi aktif degil"}
        try:
            memories = await self.memory_service.get_memories(
                self.user_id, category=category
            )
            return {
                "bilgiler": [
                    {"anahtar": m.key, "deger": m.value, "kategori": m.category}
                    for m in memories
                ]
            }
        except Exception as e:
            return {"hata": str(e)}
