"""Sesli asistan oturum yoneticisi — Gemini Live API ile bidirectional audio."""
from __future__ import annotations

import asyncio
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
    - Input:  PCM 16-bit 16kHz mono (tarayicidan)
    - Output: PCM 16-bit 24kHz mono (Gemini'den)
    - AUDIO modunda text output = thinking (ic dusunce), ses degildir.
    - Transcript: input/output_transcription ile gelir (varsa).
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
        self._gemini_ctx = None
        self._running = False
        self._turn_count = 0
        self._conversation_text: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
            try:
                memory_context = await self.memory_service.format_for_prompt(self.user_id)
                if memory_context:
                    system_prompt = f"{system_prompt}\n\n{memory_context}"
            except Exception as e:
                logger.warning(f"Memory load failed: {e}")

        # Tool tanimlari
        tool_declarations = [{"function_declarations": ALL_TOOLS}]

        # Config
        config_kwargs = {
            "response_modalities": ["AUDIO"],
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            "system_instruction": types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            "tools": tool_declarations,
        }

        # Transcription — input ve output sesinin text halini al (destekleniyorsa)
        try:
            config_kwargs["input_audio_transcription"] = types.AudioTranscriptionConfig()
            config_kwargs["output_audio_transcription"] = types.AudioTranscriptionConfig()
        except (AttributeError, TypeError):
            logger.debug("AudioTranscriptionConfig not available in this SDK version")

        config = types.LiveConnectConfig(**config_kwargs)

        # connect() async context manager dondurur
        self._gemini_ctx = client.aio.live.connect(
            model=f"models/{self.settings.gemini_live_model}",
            config=config,
        )
        self._gemini_session = await self._gemini_ctx.__aenter__()
        self._running = True

        await self._events.put({"type": "status", "state": "connected"})
        logger.info(f"Voice session {self.session_id} started (user={self.user_id})")

    async def run(self):
        """Ana dongu: audio gonder + yanit al (2 concurrent task)."""
        tasks = [
            asyncio.create_task(self._send_audio_to_gemini()),
            asyncio.create_task(self._receive_from_gemini()),
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            if self._running:
                logger.error(f"Voice session error: {e}")
                try:
                    await self._events.put({"type": "error", "message": str(e)})
                except Exception:
                    pass
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    async def stop(self):
        """Oturumu kapat."""
        self._running = False

        # Sentinel'leri non-blocking gonder
        for q in (self._audio_in, self._audio_out, self._events):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

        # Gemini baglantisini kapat
        if self._gemini_ctx:
            try:
                await self._gemini_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._gemini_session = None
            self._gemini_ctx = None

        # Hafiza cikarimi (oturum sonunda)
        if self.memory_service and self._conversation_text:
            try:
                full_text = "\n".join(self._conversation_text[-50:])  # Son 50 satir
                await self.memory_service.extract_and_store(
                    self.user_id, full_text, self.session_id
                )
            except Exception as e:
                logger.warning(f"Memory extraction failed: {e}")

        logger.info(f"Voice session {self.session_id} stopped ({self._turn_count} turns)")

    # ------------------------------------------------------------------
    # Public queue accessors
    # ------------------------------------------------------------------

    async def feed_audio(self, chunk: bytes):
        """WebSocket'ten gelen PCM audio verisini kuyruga ekle."""
        if self._running:
            try:
                self._audio_in.put_nowait(chunk)
            except asyncio.QueueFull:
                pass  # Frame drop — kuyruk dolu

    async def output_audio_stream(self):
        """Gemini'den gelen audio chunk'larini yield et."""
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._audio_out.get(), timeout=1.0)
                if chunk is None:
                    break
                yield chunk
            except asyncio.TimeoutError:
                continue

    async def event_stream(self):
        """JSON event'lerini yield et."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._events.get(), timeout=1.0)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------
    # Internal: Gemini I/O tasks
    # ------------------------------------------------------------------

    async def _send_audio_to_gemini(self):
        """Audio kuyrugunu Gemini'ye realtime_input olarak gonder."""
        from google.genai import types

        while self._running:
            try:
                chunk = await asyncio.wait_for(self._audio_in.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if chunk is None:
                break
            try:
                await self._gemini_session.send_realtime_input(
                    media=types.Blob(data=chunk, mime_type="audio/pcm")
                )
            except Exception as e:
                logger.warning(f"Send audio error: {e}")
                if "closed" in str(e).lower() or "cancel" in str(e).lower():
                    break

    async def _receive_from_gemini(self):
        """Gemini'den gelen yanitlari isle: audio + thinking + transcript + tool call."""
        from google.genai import types

        try:
            async for response in self._gemini_session.receive():
                if not self._running:
                    break

                # --- Server content (audio, text, turn signals, transcription) ---
                server_content = getattr(response, "server_content", None)
                if server_content:
                    # Model turn — audio parcalari ve thinking text
                    model_turn = getattr(server_content, "model_turn", None)
                    if model_turn and hasattr(model_turn, "parts") and model_turn.parts:
                        for part in model_turn.parts:
                            # Audio data → playback kuyrugununa
                            if hasattr(part, "inline_data") and part.inline_data:
                                data = part.inline_data.data
                                if isinstance(data, bytes) and len(data) > 0:
                                    logger.debug(f"Audio chunk: {len(data)} bytes")
                                    await self._audio_out.put(data)

                            # AUDIO modunda text = thinking (ic dusunce, ses degildir)
                            if hasattr(part, "text") and part.text:
                                self._conversation_text.append(f"AI (dusunce): {part.text}")
                                await self._events.put({
                                    "type": "thinking",
                                    "text": part.text,
                                })

                    # Turn complete — model konusmayi bitirdi
                    if getattr(server_content, "turn_complete", False):
                        self._turn_count += 1
                        await self._events.put({"type": "turn_complete"})
                        logger.debug(f"Turn {self._turn_count} complete")

                    # Output transcription — modelin soyledigi sesin text hali
                    output_tr = getattr(server_content, "output_transcription", None)
                    if output_tr:
                        text = getattr(output_tr, "text", "")
                        if text and text.strip():
                            self._conversation_text.append(f"AI: {text}")
                            await self._events.put({
                                "type": "transcript",
                                "role": "assistant",
                                "text": text,
                            })

                    # Input transcription — kullanicinin soyledigi sesin text hali
                    input_tr = getattr(server_content, "input_transcription", None)
                    if input_tr:
                        text = getattr(input_tr, "text", "")
                        if text and text.strip():
                            self._conversation_text.append(f"User: {text}")
                            await self._events.put({
                                "type": "transcript",
                                "role": "user",
                                "text": text,
                            })

                # --- Tool call ---
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

                        await self._events.put({
                            "type": "tool_result",
                            "name": fc.name,
                            "result": result,
                        })

                        # Sonucu Gemini'ye geri gonder (id gerekli)
                        await self._gemini_session.send_tool_response(
                            function_responses=[types.FunctionResponse(
                                id=fc.id,
                                name=fc.name,
                                response=result,
                            )]
                        )

        except Exception as e:
            if self._running:
                logger.error(f"Receive error: {e}", exc_info=True)
                try:
                    await self._events.put({"type": "error", "message": str(e)})
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

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
