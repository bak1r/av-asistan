"""WebSocket endpoint — sesli asistan icin /ws/voice."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from avukat.memory.service import MemoryService
from avukat.voice.session import VoiceSessionManager

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    """
    Bidirectional WebSocket: browser <-> VoiceSessionManager <-> Gemini Live.

    Protocol:
      Client -> Server:
        - Binary frames: PCM 16-bit 16 kHz mono audio
        - Text frames: JSON control messages {"type": "start"|"stop"|"ping"}
      Server -> Client:
        - Binary frames: PCM 16-bit 24 kHz mono audio (Gemini output)
        - Text frames: JSON events {"type": "transcript"|"tool_call"|"tool_result"|"status"|"error"}
    """
    await ws.accept()

    app = ws.app
    settings = app.state.settings

    if not settings.voice_enabled:
        await ws.send_json({"type": "error", "message": "Sesli asistan devre disi."})
        await ws.close(code=4000, reason="Voice disabled")
        return

    if not settings.google_api_key:
        await ws.send_json({"type": "error", "message": "Google API anahtari ayarlanmamis."})
        await ws.close(code=4001, reason="No API key")
        return

    # Memory service (opsiyonel)
    memory_svc = None
    if settings.memory_enabled:
        memory_svc = MemoryService(
            session_factory=app.state.session_factory,
            llm=app.state.llm,
        )

    session = VoiceSessionManager(
        settings=settings,
        embedder=app.state.embedder,
        text_llm=app.state.llm,
        session_factory=app.state.session_factory,
        memory_service=memory_svc,
        user_id="default",
    )

    tasks: list[asyncio.Task] = []
    try:
        # Gemini'ye baglan
        await session.start()
        await ws.send_json({"type": "status", "state": "connected", "session_id": session.session_id})

        # 4 concurrent task
        tasks = [
            asyncio.create_task(session.run()),
            asyncio.create_task(_forward_audio_out(ws, session)),
            asyncio.create_task(_forward_events(ws, session)),
            asyncio.create_task(_receive_from_client(ws, session)),
        ]
        # Herhangi biri bitince hepsini durdur
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        # Hatalari kontrol et
        for t in done:
            if t.exception() and not isinstance(t.exception(), (asyncio.CancelledError, WebSocketDisconnect)):
                logger.error(f"Voice WS task error: {t.exception()}")

    except WebSocketDisconnect:
        logger.info(f"Voice WS disconnected: {session.session_id}")
    except Exception as e:
        logger.error(f"Voice WS error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await session.stop()
        try:
            await ws.close()
        except Exception:
            pass


async def _receive_from_client(ws: WebSocket, session: VoiceSessionManager):
    """Client'tan gelen audio ve control mesajlarini isle."""
    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.disconnect":
                break

            # Binary = PCM audio
            if "bytes" in message and message["bytes"]:
                await session.feed_audio(message["bytes"])

            # Text = JSON control
            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "stop":
                        break
                    elif msg_type == "ping":
                        await ws.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Client receive error: {e}")


async def _forward_audio_out(ws: WebSocket, session: VoiceSessionManager):
    """Gemini'den gelen audio'yu client'a ilet."""
    try:
        async for chunk in session.output_audio_stream():
            await ws.send_bytes(chunk)
    except Exception as e:
        logger.debug(f"Audio forward ended: {e}")


async def _forward_events(ws: WebSocket, session: VoiceSessionManager):
    """Gemini event'lerini client'a JSON olarak ilet."""
    try:
        async for event in session.event_stream():
            await ws.send_json(event)
    except Exception as e:
        logger.debug(f"Event forward ended: {e}")
