"""Windows System Media Transport Controls (SMTC) integration for Jarvis Dynamic Island.

Provides real-time tracking of active media playback (Spotify, Chrome, Edge, YouTube, Apple Music),
track metadata (title, artist, album, duration, position), and controls (play, pause, next, prev).
Runs asynchronously on a background worker with zero overhead on the Tkinter main thread.
"""
from __future__ import annotations

import asyncio
import io
import sys
import threading
import time
from typing import Callable, Optional

_HAS_WINRT = False
if sys.platform == "win32":
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as _MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PlaybackStatus,
        )
        from winrt.windows.storage.streams import DataReader as _DataReader
        _HAS_WINRT = True
    except Exception:
        _HAS_WINRT = False


class MediaState:
    def __init__(self):
        self.is_playing: bool = False
        self.title: str = ""
        self.artist: str = ""
        self.album: str = ""
        self.source_app: str = ""
        self.position: float = 0.0
        self.duration: float = 0.0
        self.has_thumbnail: bool = False
        self.last_updated: float = 0.0

    @property
    def is_active(self) -> bool:
        """Returns True if there is a known track and it is actively playing or recently paused."""
        return bool(self.title) and (self.is_playing or (time.time() - self.last_updated < 15.0))


class MediaSentinel:
    """Monitors system media in a background thread and exposes thread-safe state and actions."""

    def __init__(self, on_update_callback: Optional[Callable[[MediaState], None]] = None):
        self.on_update = on_update_callback
        self.state = MediaState()
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._manager = None
        self._session = None

    def start(self):
        if not _HAS_WINRT or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_thread, daemon=True, name="JarvisMediaSentinel")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def get_state(self) -> MediaState:
        with self._lock:
            # Copy snapshot
            st = MediaState()
            st.is_playing = self.state.is_playing
            st.title = self.state.title
            st.artist = self.state.artist
            st.album = self.state.album
            st.source_app = self.state.source_app
            st.position = self.state.position
            st.duration = self.state.duration
            st.last_updated = self.state.last_updated
            return st

    def toggle_play_pause(self):
        if not _HAS_WINRT:
            return
        self._dispatch_async_cmd("toggle")

    def next_track(self):
        if not _HAS_WINRT:
            return
        self._dispatch_async_cmd("next")

    def prev_track(self):
        if not _HAS_WINRT:
            return
        self._dispatch_async_cmd("prev")

    def _dispatch_async_cmd(self, cmd: str):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._run_cmd(cmd), self._loop)

    async def _run_cmd(self, cmd: str):
        try:
            if not self._manager:
                self._manager = await _MediaManager.request_async()
            session = self._manager.get_current_session() if self._manager else None
            if not session:
                return
            if cmd == "toggle":
                await session.try_toggle_play_pause_async()
            elif cmd == "next":
                await session.try_skip_next_async()
            elif cmd == "prev":
                await session.try_skip_previous_async()
        except Exception:
            pass

    def _worker_thread(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._poll_loop())
        except (asyncio.CancelledError, RuntimeError):
            pass
        except Exception:
            pass
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    async def _poll_loop(self):
        while self._running:
            try:
                if not self._manager:
                    self._manager = await _MediaManager.request_async()
                
                if self._manager:
                    session = self._manager.get_current_session()
                    self._session = session
                    if session:
                        info = session.get_playback_info()
                        status = info.playback_status if info else None
                        is_playing = (status == _PlaybackStatus.PLAYING)

                        # Source app user model id
                        app_id = session.source_app_user_model_id or ""
                        # Extract friendly app name
                        friendly_app = "Media"
                        app_lower = app_id.lower()
                        if "spotify" in app_lower:
                            friendly_app = "Spotify"
                        elif "chrome" in app_lower:
                            friendly_app = "Chrome"
                        elif "edge" in app_lower:
                            friendly_app = "Edge"
                        elif "brave" in app_lower:
                            friendly_app = "Brave"
                        elif "vlc" in app_lower:
                            friendly_app = "VLC"
                        elif "music" in app_lower:
                            friendly_app = "Apple Music"

                        timeline = session.get_timeline_properties()
                        pos = timeline.position.total_seconds() if timeline and timeline.position else 0.0
                        dur = timeline.end_time.total_seconds() if timeline and timeline.end_time else 0.0

                        props = await session.try_get_media_properties_async()
                        title = (props.title if props else "") or ""
                        artist = (props.artist if props else "") or (props.album_artist if props else "") or ""
                        album = (props.album_title if props else "") or ""

                        changed = False
                        with self._lock:
                            if (self.state.is_playing != is_playing or
                                self.state.title != title or
                                self.state.artist != artist or
                                abs(self.state.position - pos) > 2.0):
                                changed = True
                            
                            self.state.is_playing = is_playing
                            self.state.title = title
                            self.state.artist = artist
                            self.state.album = album
                            self.state.source_app = friendly_app
                            self.state.position = pos
                            self.state.duration = dur
                            self.state.last_updated = time.time()

                        if changed and self.on_update:
                            try:
                                self.on_update(self.get_state())
                            except Exception:
                                pass
                    else:
                        with self._lock:
                            if self.state.is_playing:
                                self.state.is_playing = False
                                if self.on_update:
                                    try:
                                        self.on_update(self.get_state())
                                    except Exception:
                                        pass
            except Exception:
                pass
            
            await asyncio.sleep(0.5)


_GLOBAL_SENTINEL: Optional[MediaSentinel] = None

def get_media_sentinel(on_update: Optional[Callable[[MediaState], None]] = None) -> MediaSentinel:
    global _GLOBAL_SENTINEL
    if _GLOBAL_SENTINEL is None:
        _GLOBAL_SENTINEL = MediaSentinel(on_update)
        _GLOBAL_SENTINEL.start()
    return _GLOBAL_SENTINEL
