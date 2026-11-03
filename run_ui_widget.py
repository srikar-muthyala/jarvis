#!/usr/bin/env python3
"""Run Jarvis Modern Dynamic Island as a true transparent desktop widget.

Uses Windows WebView2 with frameless=True, transparent=True, on_top=True.
Zero window chrome, zero borders, floating on top of desktop.
"""
from __future__ import annotations

import os
import sys
import time
import threading
import urllib.request
from pathlib import Path

import webview

HERE = Path(__file__).resolve().parent


def is_bridge_ready() -> bool:
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8765/ui", timeout=1)
        return req.status == 200
    except Exception:
        return False


def start_bridge_thread():
    import bridge
    bridge.main()


def main():
    os.chdir(HERE)

    # Ensure backend bridge is running
    if not is_bridge_ready():
        print("[Widget] Starting Jarvis WebSocket bridge in background...")
        t = threading.Thread(target=start_bridge_thread, daemon=True)
        t.start()
        for _ in range(40):
            time.sleep(0.25)
            if is_bridge_ready():
                break

    # Screen metrics for top-center placement
    win_w = 540
    win_h = 560
    screens = webview.screens
    if screens:
        s = screens[0]
        win_x = int((s.width - win_w) / 2)
        win_y = 12
    else:
        win_x = 400
        win_y = 12

    print(f"[Widget] Launching native transparent desktop widget at ({win_x}, {win_y})...")
    window = webview.create_window(
        title="J.A.R.V.I.S. Dynamic Island",
        url="http://127.0.0.1:8765/ui",
        width=win_w,
        height=win_h,
        x=win_x,
        y=win_y,
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=True,
        shadow=False,
        background_color="#000000",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
