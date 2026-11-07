"""System Sentinel for Jarvis Dynamic Island.

Provides:
- Universal Global Microphone Mute Sentinel (Ctrl+Alt+M) with on-island indicator.
- Dynamic Volume HUD monitoring and controls (smooth island slider popups on volume change).
- Cached, high-performance COM audio endpoints with zero GC overhead.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from typing import Callable, Optional

_HAS_AUDIO = False
if sys.platform == "win32":
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        _HAS_AUDIO = True
    except Exception:
        _HAS_AUDIO = False


class SystemSentinel:
    """Monitors system master volume and microphone mute status."""

    def __init__(
        self,
        on_volume_changed: Optional[Callable[[int, bool], None]] = None,
        on_mic_changed: Optional[Callable[[bool], None]] = None,
    ):
        self.on_volume_changed = on_volume_changed
        self.on_mic_changed = on_mic_changed
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._vol_ctrl = None
        self._mic_ctrl = None
        self._last_vol: int = -1
        self._last_vol_muted: bool = False
        self._last_mic_muted: bool = False
        self._inited = False
        self._lock = threading.Lock()

    def start(self):
        if not _HAS_AUDIO or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="JarvisSystemSentinel")
        self._thread.start()

    def stop(self):
        self._running = False

    def _ensure_audio_ctrls(self):
        if not _HAS_AUDIO:
            return
        try:
            import comtypes
            comtypes.CoInitialize()
            if self._vol_ctrl is None:
                spk = AudioUtilities.GetSpeakers()
                self._vol_ctrl = spk.EndpointVolume
            if self._mic_ctrl is None:
                mic = AudioUtilities.GetMicrophone()
                if mic:
                    iface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    self._mic_ctrl = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
        except Exception:
            pass

    def get_volume(self) -> tuple[int, bool]:
        """Returns (volume_percent, is_muted)."""
        if not _HAS_AUDIO:
            return 50, False
        with self._lock:
            try:
                self._ensure_audio_ctrls()
                if self._vol_ctrl:
                    pct = int(round(self._vol_ctrl.GetMasterVolumeLevelScalar() * 100))
                    muted = bool(self._vol_ctrl.GetMute())
                    return pct, muted
            except Exception:
                pass
        return 50, False

    def set_volume(self, pct: int):
        """Sets volume from 0 to 100."""
        if not _HAS_AUDIO:
            return
        with self._lock:
            try:
                self._ensure_audio_ctrls()
                if self._vol_ctrl:
                    val = max(0.0, min(1.0, pct / 100.0))
                    self._vol_ctrl.SetMasterVolumeLevelScalar(val, None)
            except Exception:
                pass

    def get_mic_mute(self) -> bool:
        """Returns True if the system default microphone is muted."""
        if not _HAS_AUDIO:
            return False
        with self._lock:
            try:
                self._ensure_audio_ctrls()
                if self._mic_ctrl:
                    return bool(self._mic_ctrl.GetMute())
            except Exception:
                pass
        return False

    def set_mic_mute(self, muted: bool) -> bool:
        """Sets microphone mute state. Returns the new mute state."""
        if not _HAS_AUDIO:
            return False
        with self._lock:
            try:
                self._ensure_audio_ctrls()
                if self._mic_ctrl:
                    self._mic_ctrl.SetMute(1 if muted else 0, None)
                    return bool(self._mic_ctrl.GetMute())
            except Exception:
                pass
        return False

    def toggle_mic_mute(self) -> bool:
        """Toggles system mic mute state. Returns the new state (True = Muted)."""
        cur = self.get_mic_mute()
        new_state = not cur
        return self.set_mic_mute(new_state)

    def _monitor_loop(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass

        self._ensure_audio_ctrls()

        # Initial baseline
        try:
            vol, vol_m = self.get_volume()
            mic_m = self.get_mic_mute()
            self._last_vol = vol
            self._last_vol_muted = vol_m
            self._last_mic_muted = mic_m
            self._inited = True
        except Exception:
            pass

        while self._running:
            try:
                vol, vol_m = self.get_volume()
                if self._inited and (vol != self._last_vol or vol_m != self._last_vol_muted):
                    self._last_vol = vol
                    self._last_vol_muted = vol_m
                    if self.on_volume_changed:
                        self.on_volume_changed(vol, vol_m)

                mic_m = self.get_mic_mute()
                if self._inited and (mic_m != self._last_mic_muted):
                    self._last_mic_muted = mic_m
                    if self.on_mic_changed:
                        self.on_mic_changed(mic_m)
            except Exception:
                pass

            time.sleep(0.2)


_GLOBAL_SYS_SENTINEL: Optional[SystemSentinel] = None

def get_system_sentinel(
    on_vol: Optional[Callable[[int, bool], None]] = None,
    on_mic: Optional[Callable[[bool], None]] = None
) -> SystemSentinel:
    global _GLOBAL_SYS_SENTINEL
    if _GLOBAL_SYS_SENTINEL is None:
        _GLOBAL_SYS_SENTINEL = SystemSentinel(on_vol, on_mic)
        _GLOBAL_SYS_SENTINEL.start()
    return _GLOBAL_SYS_SENTINEL
