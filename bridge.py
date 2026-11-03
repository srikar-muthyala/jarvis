#!/usr/bin/env python3
"""Jarvis UI WebSocket Bridge.

Connects the Tauri v2 / React modern UI to the Jarvis Assistant engine.
Exposes WebSocket at ws://127.0.0.1:8765
Optionally serves the built frontend from jarvis-ui/dist on http://127.0.0.1:8765
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path

from aiohttp import web, WSMsgType

from actions import Context
from audio import ConsoleSpeaker, Speaker
from commands import load_apps
from jarvis import Assistant, load_env
from llm import LLM

HERE = Path(__file__).resolve().parent
DIST_DIR = HERE / "jarvis-ui" / "dist"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jarvis-bridge")

clients: set[web.WebSocketResponse] = set()
asst: Assistant | None = None
main_loop: asyncio.AbstractEventLoop | None = None

# Current assistant state snapshot
current_state = {
    "connected": True,
    "statusLabel": "Ready",
    "statusColor": "#a3a3a3",
    "mood": "online",
    "lastQuery": "",
    "lastReply": "Welcome back, sir. All systems nominal.",
    "isListening": False,
    "isThinking": False,
    "isSpeaking": False,
    "hasApproval": False,
    "approvalPrompt": "",
    "telemetry": {
        "cpu": 15,
        "ram": 50,
        "bat": "100%",
        "batLevel": 100,
        "charging": True,
    },
}


def get_live_telemetry() -> dict:
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        bat = psutil.sensors_battery()
        if bat:
            bat_pct = int(bat.percent)
            charging = bool(bat.power_plugged)
            bat_str = f"{bat_pct}%" + (" (Charging)" if charging else "")
        else:
            bat_pct = 100
            charging = True
            bat_str = "AC Power"
        return {
            "cpu": cpu,
            "ram": mem,
            "bat": bat_str,
            "batLevel": bat_pct,
            "charging": charging,
        }
    except Exception:
        return {
            "cpu": 16,
            "ram": 48,
            "bat": "95%",
            "batLevel": 95,
            "charging": True,
        }


async def broadcast_state(partial_state: dict):
    """Update current state and notify all connected WebSocket clients."""
    current_state.update(partial_state)
    if not clients:
        return
    msg = json.dumps({"type": "state_update", "payload": current_state})
    to_remove = set()
    for ws in list(clients):
        if ws.closed:
            to_remove.add(ws)
            continue
        try:
            await ws.send_str(msg)
        except Exception:
            to_remove.add(ws)
    for ws in to_remove:
        clients.discard(ws)


def broadcast_from_thread(partial_state: dict):
    """Threadsafe helper to schedule state broadcasts on the async event loop."""
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_state(partial_state), main_loop)


def setup_assistant() -> Assistant:
    global asst
    load_env(HERE / ".env")

    backend = os.environ.get("TTS_BACKEND", "edge").lower().strip()
    voice = os.environ.get("TTS_VOICE", "en-GB-RyanNeural").strip()

    try:
        speaker = Speaker(name="Jarvis", voice_hint=voice)
    except Exception:
        speaker = ConsoleSpeaker(name="Jarvis")

    apps = load_apps(HERE / "apps.json")
    name = os.environ.get("ASSISTANT_NAME", "Jarvis")
    llm = LLM(
        api_key=os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        model=os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite"),
        name=name,
    )
    names = ["jarvis", "assistant"]
    asst = Assistant(speaker, apps, llm, names, dry_run=False)

    # Intercept speak to update modern UI state
    orig_speak = asst.speaker.speak

    def bridged_speak(reply: str):
        if not reply:
            return
        logger.info(f"Jarvis speaking: {reply[:60]}...")
        is_approval = bool(
            re.search(
                r"(?:open (?:the |that )?(?:link|website|page|site|url)|shall i open|would you like me to open)",
                reply,
                re.IGNORECASE,
            )
        )
        broadcast_from_thread({
            "isSpeaking": True,
            "isThinking": False,
            "statusLabel": "Speaking",
            "statusColor": "#10b981",
            "mood": "speaking",
            "lastReply": reply,
            "hasApproval": is_approval,
            "approvalPrompt": reply if is_approval else "",
        })
        try:
            orig_speak(reply)
        finally:
            broadcast_from_thread({
                "isSpeaking": False,
                "statusLabel": "Ready",
                "statusColor": "#a3a3a3",
                "mood": "online",
            })

    asst.speaker.speak = bridged_speak
    return asst


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    logger.info("UI Client connected to WebSocket")

    # Send initial state snapshot
    await ws.send_str(json.dumps({"type": "state_update", "payload": current_state}))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")

                    if msg_type == "query":
                        text = data.get("text", "").strip()
                        if text and asst:
                            await broadcast_state({
                                "lastQuery": text,
                                "isThinking": True,
                                "statusLabel": "Thinking",
                                "statusColor": "#f59e0b",
                                "mood": "thinking",
                                "hasApproval": False,
                            })
                            # Execute assistant query in background executor
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, asst.handle, text)

                    elif msg_type == "approval":
                        accepted = bool(data.get("accepted", False))
                        cmd = "yes" if accepted else "no"
                        await broadcast_state({"hasApproval": False})
                        if asst:
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, asst.handle, cmd)

                    elif msg_type == "stop_speech":
                        if asst and hasattr(asst, "speaker"):
                            asst.speaker.stop()
                        await broadcast_state({
                            "isSpeaking": False,
                            "statusLabel": "Ready",
                            "statusColor": "#a3a3a3",
                            "mood": "online",
                        })

                    elif msg_type == "mic_click":
                        # Voice query trigger
                        await broadcast_state({
                            "isListening": True,
                            "statusLabel": "Listening",
                            "statusColor": "#ef4444",
                            "mood": "listening",
                        })
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
            elif msg.type == WSMsgType.ERROR:
                logger.warning(f"WebSocket closed with error {ws.exception()}")
    finally:
        clients.discard(ws)
        logger.info("UI Client disconnected")
    return ws


async def telemetry_loop():
    """Background task pushing live CPU, RAM, and Battery every 1.5 seconds."""
    while True:
        try:
            telem = get_live_telemetry()
            await broadcast_state({"telemetry": telem})
        except Exception:
            pass
        await asyncio.sleep(1.5)


async def on_startup(app: web.Application):
    global main_loop
    main_loop = asyncio.get_running_loop()
    app["telemetry_task"] = asyncio.create_task(telemetry_loop())


async def on_cleanup(app: web.Application):
    app["telemetry_task"].cancel()
    for ws in list(clients):
        await ws.close()


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # WebSocket route
    app.router.add_get("/ws", ws_handler)

    # If built frontend exists, serve it
    if DIST_DIR.exists():
        app.router.add_static("/assets", DIST_DIR / "assets")
        async def serve_index(request):
            if request.headers.get("Upgrade", "").lower() == "websocket":
                return await ws_handler(request)
            return web.FileResponse(DIST_DIR / "index.html")
        app.router.add_get("/ui", serve_index)
        app.router.add_get("/", serve_index)
    else:
        app.router.add_get("/", ws_handler)

    return app


def main():
    logger.info("Starting Jarvis Core Engine...")
    setup_assistant()
    logger.info("Starting WebSocket Bridge on http://127.0.0.1:8765...")
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=8765, access_log=None)


if __name__ == "__main__":
    main()
