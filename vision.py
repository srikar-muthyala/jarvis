"""Vision and screen perception for Jarvis using Win32 GDI / Pillow and Gemini Multimodal."""
from __future__ import annotations

import base64
import ctypes
import io
import os
import re
import sys
import time
from PIL import Image

user32 = getattr(ctypes, "windll", None).user32 if hasattr(ctypes, "windll") else None
gdi32 = getattr(ctypes, "windll", None).gdi32 if hasattr(ctypes, "windll") else None


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', ctypes.c_uint32),
        ('biWidth', ctypes.c_int32),
        ('biHeight', ctypes.c_int32),
        ('biPlanes', ctypes.c_uint16),
        ('biBitCount', ctypes.c_uint16),
        ('biCompression', ctypes.c_uint32),
        ('biSizeImage', ctypes.c_uint32),
        ('biXPelsPerMeter', ctypes.c_int32),
        ('biYPelsPerMeter', ctypes.c_int32),
        ('biClrUsed', ctypes.c_uint32),
        ('biClrImportant', ctypes.c_uint32)
    ]


def capture_screen_image() -> Image.Image | None:
    """Capture screen image via Windows GDI (fastest on Windows) or Pillow ImageGrab (Linux/macOS)."""
    if user32 and gdi32:
        try:
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            gdi32.SelectObject(hdc_mem, hbmp)
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

            user32.ReleaseDC(0, hdc_screen)
            gdi32.DeleteDC(hdc_mem)
            gdi32.DeleteObject(hbmp)

            img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')
            return img
        except Exception as e:
            print(f"  [win32 vision capture error: {e}]")

    # Cross-platform fallback (Linux, macOS, or if GDI fails)
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception as e:
        print(f"  [vision capture fallback error: {e}]")
        return None


def analyze_screen(prompt: str, api_key: str, model: str = "gemini-3.5-flash") -> str:
    """Analyze current screen content with Gemini Vision."""
    import requests
    import urllib3
    urllib3.disable_warnings()

    img = capture_screen_image()
    if img is None:
        return "I was unable to capture your screen, sir."

    try:
        # Resize to 720p max to optimize upload speed and latency
        img.thumbnail((1280, 720))
        bio = io.BytesIO()
        img.save(bio, format="JPEG", quality=82)
        b64_data = base64.b64encode(bio.getvalue()).decode("utf-8")

        clean_prompt = prompt or "Describe what is currently visible on my screen and highlight anything important."
        system_instructions = (
            "You are J.A.R.V.I.S., Tony Stark's sophisticated British AI assistant. "
            "Analyze the user's screen image accurately and answer their query in 2 to 3 natural, concise spoken sentences. "
            "Never use markdown, asterisks, bullet points, or emojis."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": f"{system_instructions}\n\nUser request: {clean_prompt}"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_data}}
                ]
            }],
            "generationConfig": {"maxOutputTokens": 200}
        }

        # Try with automatic retry for transient 503 (Service Unavailable)
        last_status = None
        for attempt in range(2):
            r = requests.post(url, json=payload, verify=False, timeout=18)
            last_status = r.status_code
            if r.status_code == 200:
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    text = re.sub(r"[*#_`]", "", text).strip()
                    return text or "I have inspected your display, sir. Everything appears normal."
            elif r.status_code == 503 and attempt == 0:
                time.sleep(1.2)
                continue
            break

        if last_status == 503:
            return "The Gemini vision servers are temporarily busy, sir. Please try again in a moment."
        return f"Visual diagnostics encountered an issue (Status {last_status}), sir."
    except Exception as e:
        print(f"  [vision error: {e}]")
        return "I encountered an error while analyzing your visual display, sir."
