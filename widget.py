#!/usr/bin/env python3
"""TwoCode-Style Dynamic Island Widget for Jarvis.

Authentic implementation of the twocode.nl island for Windows:
- Minimalist top-docked resting notch with expressive Robo mascot.
- Smooth damped spring physics with organic elastic overshoot.
- Hover-peek blooming from compact notch to quick glance preview.
- TwoCode expanded card grid:
  - Left: AI Assistant card with Robo face, status, unified dark input, and interactive approval chips.
  - Right top: Clock & Date card.
  - Right bottom: Battery & System Health card (with proactive 25% charger suggestion).
- Instant Barge-In interruption (Escape, voice, or click).
"""
from __future__ import annotations

import datetime
import math
import os
import random
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageTk

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from jarvis import Assistant, load_env
from commands import load_apps
from actions import Context, TimerManager
from llm import LLM
import media_controller
import system_sentinel


def get_system_telemetry() -> dict[str, str]:
    try:
        import psutil
        cpu = int(round(psutil.cpu_percent()))
        mem = int(round(psutil.virtual_memory().percent))
        bat = psutil.sensors_battery()
        if bat:
            percent = int(round(bat.percent))
            plugged = bat.power_plugged
            if plugged:
                status = "Charging"
            elif percent <= 10:
                status = "Critical!"
            elif percent <= 15:
                status = "Very Low!"
            elif percent <= 20:
                status = "Very Low"
            elif percent <= 25:
                status = "Low"
            else:
                status = "Discharging"
            bat_str = f"{percent}% {status}"
        else:
            bat_str = "AC Power"
        return {"cpu": f"{cpu}%", "ram": f"{mem}%", "bat": bat_str}
    except Exception:
        return {"cpu": "14%", "ram": "48%", "bat": "88% AC"}


class WobnimoSpring:
    """Damped harmonic spring solver for organic squash, stretch, and recoil."""
    def __init__(self, val: float = 0.0, k: float = 260.0, c: float = 22.0):
        self.x = val
        self.target = val
        self.v = 0.0
        self.k = k
        self.c = c

    def update(self, dt: float):
        # Stable semi-implicit Euler integration
        f = -self.k * (self.x - self.target) - self.c * self.v
        self.v += f * dt
        self.x += self.v * dt

    def impulse(self, amt: float):
        self.v += amt


class WobnimoMascot:
    """Lively 3D TwoCode Robo mascot with spring physics, procedural blinks, and gaze tracking."""
    def __init__(self):
        self.squash = WobnimoSpring(1.0, k=280.0, c=20.0)      # X scale (squash/stretch)
        self.antenna_tilt = WobnimoSpring(0.0, k=220.0, c=16.0) # Antenna angle
        self.gaze_x = WobnimoSpring(0.0, k=180.0, c=18.0)
        self.gaze_y = WobnimoSpring(0.0, k=180.0, c=18.0)

        # Procedural Blink state
        self.next_blink = time.perf_counter() + random.uniform(2.0, 4.5)
        self.blink_start = 0.0
        self.blinking = False
        self.blink_val = 1.0  # 1.0 = fully open, 0.05 = closed slit
        self.is_double = False

        # Natural gaze saccade timer
        self.next_saccade = time.perf_counter() + 3.0

        # Celebration timer
        self.celebrate_until = 0.0

        # References to prevent garbage collection in Tkinter
        self._ref_compact = None
        self._ref_expanded = None

    @property
    def is_celebrating(self) -> bool:
        return time.perf_counter() < self.celebrate_until

    def trigger_celebrate(self, duration: float = 2.2):
        self.celebrate_until = time.perf_counter() + duration
        self.squash.impulse(12.0)
        self.antenna_tilt.impulse(18.0)

    def trigger_click_wobble(self):
        """Squash down on interaction and spring recoil."""
        self.squash.impulse(14.0)
        self.antenna_tilt.impulse(random.choice([-16.0, 16.0]))

    def trigger_hover(self):
        """Perk up slightly on mouse hover."""
        self.squash.impulse(-6.0)

    def update(self, dt: float, mood: str, is_speaking: bool, is_listening: bool, audio_level: float = 0.0):
        now = time.perf_counter()

        # 1. Step spring physics
        self.squash.update(dt)
        self.antenna_tilt.update(dt)
        self.gaze_x.update(dt)
        self.gaze_y.update(dt)

        # 2. Audio-reactive bounce during speech
        if is_speaking:
            if audio_level > 0.12:
                bounce_factor = (audio_level - 0.12) * 5.0
                self.squash.impulse(bounce_factor)
                self.antenna_tilt.impulse((random.random() - 0.5) * 8.0)

        # 3. Gaze management based on mood
        if mood in ("thinking", "working"):
            self.gaze_x.target = 1.6
            self.gaze_y.target = -1.8
        elif mood == "listening":
            self.gaze_x.target = 0.0
            self.gaze_y.target = 0.0
        elif mood == "sleeping":
            self.gaze_x.target = 0.0
            self.gaze_y.target = 1.0
        elif mood == "celebrating":
            self.gaze_x.target = 0.0
            self.gaze_y.target = -0.6
        else: # idle
            if now >= self.next_saccade:
                self.next_saccade = now + random.uniform(2.5, 6.0)
                self.gaze_x.target = random.choice([-1.2, 0.0, 0.0, 1.2])
                self.gaze_y.target = random.choice([-0.8, 0.0, 0.0, 0.8])

        # 4. Blink cycle
        if not self.blinking:
            if now >= self.next_blink and mood != "sleeping":
                self.blinking = True
                self.blink_start = now
                self.is_double = (random.random() < 0.22)
        else:
            dur = 0.22 if self.is_double else 0.14
            elapsed = now - self.blink_start
            if elapsed >= dur:
                self.blinking = False
                self.blink_val = 1.0
                self.next_blink = now + random.uniform(2.5, 5.5)
            else:
                p = elapsed / dur
                if self.is_double:
                    p2 = p * 2.0
                    if p2 > 1.0:
                        p2 -= 1.0
                    self.blink_val = max(0.06, abs(math.cos(p2 * math.pi)))
                else:
                    self.blink_val = max(0.06, abs(math.cos(p * math.pi)))

        if mood == "sleeping":
            self.blink_val = 0.08  # Soft drooping slit

    def render_face(self, size: int = 40, mood: str = "online", scale: int = 3, phase: float = 0.0) -> Image.Image:
        s = size * scale
        cx, cy = s // 2, s // 2

        # Spring squash/stretch factors
        sq_x = max(0.72, min(1.32, self.squash.x))
        sq_y = 1.0 / math.sqrt(sq_x)  # Area conservation

        # Idle floating breath
        float_y = math.sin(phase * 1.5) * (1.8 * scale) if mood != "sleeping" else math.sin(phase * 0.7) * (0.8 * scale)
        cy = cy + float_y

        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        gdraw = ImageDraw.Draw(glow)

        # Mood-based colors
        if mood == "listening":
            eye_color = (244, 63, 94, 255)
            glow_color = (244, 63, 94, 150)
        elif mood in ("thinking", "working"):
            eye_color = (245, 158, 11, 255)
            glow_color = (245, 158, 11, 150)
        elif mood in ("done", "speaking"):
            eye_color = (16, 185, 129, 255)
            glow_color = (16, 185, 129, 150)
        elif mood in ("approval", "curious", "celebrating"):
            eye_color = (168, 85, 247, 255)
            glow_color = (168, 85, 247, 160)
        elif mood == "sleeping":
            eye_color = (130, 130, 150, 200)
            glow_color = (80, 80, 110, 80)
        else: # online / idle
            eye_color = (245, 245, 245, 255)
            glow_color = (160, 160, 170, 110)

        # 1. Ambient Glow Aura
        gdraw.ellipse([cx - s * 0.38 * sq_x, cy - s * 0.28 * sq_y, cx + s * 0.38 * sq_x, cy + s * 0.42 * sq_y], fill=glow_color)
        glow_blurred = glow.filter(ImageFilter.GaussianBlur(radius=int(5 * scale)))

        # 2. Antenna with Spring Tilt
        tilt_px = self.antenna_tilt.x * 0.08 * scale
        ant_top_x = cx + tilt_px
        ant_top_y = cy - (s * 0.44 * sq_y)
        ant_stem_w = max(2, int(s * 0.04))
        draw.line([cx, cy - (s * 0.26 * sq_y), ant_top_x, ant_top_y], fill=(200, 200, 200, 255), width=ant_stem_w)

        ant_r = s * 0.065
        draw.ellipse([ant_top_x - ant_r, ant_top_y - ant_r, ant_top_x + ant_r, ant_top_y + ant_r], fill=(255, 255, 255, 255), outline=eye_color, width=max(1, int(scale * 1.2)))

        # 3. Ear Cylinders
        ear_w, ear_h = s * 0.08 * sq_x, s * 0.18 * sq_y
        draw.rounded_rectangle([cx - s * 0.42 * sq_x, cy - ear_h / 2, cx - s * 0.34 * sq_x, cy + ear_h / 2], radius=int(ear_w / 2), fill=(200, 200, 200, 255))
        draw.rounded_rectangle([cx + s * 0.34 * sq_x, cy - ear_h / 2, cx + s * 0.42 * sq_x, cy + ear_h / 2], radius=int(ear_w / 2), fill=(200, 200, 200, 255))

        # 4. Head Chassis (Pure white rounded TwoCode robot chassis)
        hw = s * 0.36 * sq_x
        hh = s * 0.33 * sq_y
        head_box = [cx - hw, cy - hh * 0.9, cx + hw, cy + hh * 1.1]
        draw.ellipse(head_box, fill=(245, 245, 245, 255), outline=(190, 190, 190, 255), width=max(1, int(scale)))

        # 5. Visor Screen
        vw = s * 0.26 * sq_x
        vh = s * 0.19 * sq_y
        visor_box = [cx - vw, cy - vh * 0.7, cx + vw, cy + vh * 1.3]
        draw.rounded_rectangle(visor_box, radius=int(vh * 0.7), fill=(18, 18, 18, 255), outline=(42, 42, 42, 255), width=max(1, int(scale)))

        # Subtle visor glass glossy reflection
        draw.arc([cx - vw + scale, cy - vh * 0.7 + scale, cx + vw - scale, cy + vh * 1.3 - scale], start=190, end=350, fill=(70, 70, 70, 100), width=max(1, int(scale)))

        # 6. Eye Rendering with Blinking & Gaze
        eye_base_w = s * 0.05 * sq_x
        eye_base_h = s * 0.058 * sq_y * self.blink_val
        eye_base_h = max(1.0 * scale, eye_base_h)

        gx = self.gaze_x.x * scale
        gy = self.gaze_y.x * scale

        lx = cx - (s * 0.12 * sq_x) + gx
        rx = cx + (s * 0.12 * sq_x) + gx
        ey = cy + (s * 0.04 * sq_y) + gy

        if mood in ("done", "speaking") and self.blink_val > 0.4:
            # Happy curved arc eyes (Wobnimo smile)
            arc_w = max(2, int(s * 0.038))
            draw.arc([lx - eye_base_w, ey - eye_base_h * 1.1, lx + eye_base_w, ey + eye_base_h * 1.1], start=200, end=340, fill=eye_color, width=arc_w)
            draw.arc([rx - eye_base_w, ey - eye_base_h * 1.1, rx + eye_base_w, ey + eye_base_h * 1.1], start=200, end=340, fill=eye_color, width=arc_w)
        elif mood in ("thinking", "working") and self.blink_val > 0.4:
            # Focused rounded rectangle eyes + orbital particle
            draw.rounded_rectangle([lx - eye_base_w * 1.1, ey - eye_base_h * 0.7, lx + eye_base_w * 1.1, ey + eye_base_h * 0.7], radius=int(eye_base_h * 0.7), fill=eye_color)
            draw.rounded_rectangle([rx - eye_base_w * 1.1, ey - eye_base_h * 0.7, rx + eye_base_w * 1.1, ey + eye_base_h * 0.7], radius=int(eye_base_h * 0.7), fill=eye_color)
            # Orbital thinking ring
            orb_r = s * 0.22
            orb_x = cx + math.cos(phase * 4.0) * orb_r
            orb_y = cy + math.sin(phase * 4.0) * (orb_r * 0.6)
            draw.ellipse([orb_x - 2 * scale, orb_y - 2 * scale, orb_x + 2 * scale, orb_y + 2 * scale], fill=(255, 215, 0, 240))
        elif mood == "celebrating":
            # Curved joyful crescent eyes
            draw.arc([lx - eye_base_w, ey - eye_base_h, lx + eye_base_w, ey + eye_base_h], start=180, end=360, fill=eye_color, width=max(2, int(s * 0.04)))
            draw.arc([rx - eye_base_w, ey - eye_base_h, rx + eye_base_w, ey + eye_base_h], start=180, end=360, fill=eye_color, width=max(2, int(s * 0.04)))
        else:
            # Dynamic blinking oval eyes
            draw.ellipse([lx - eye_base_w, ey - eye_base_h, lx + eye_base_w, ey + eye_base_h], fill=eye_color)
            draw.ellipse([rx - eye_base_w, ey - eye_base_h, rx + eye_base_w, ey + eye_base_h], fill=eye_color)

            # Pupil highlight reflection (adds depth and life)
            if self.blink_val > 0.6:
                hr = max(1, int(scale * 1.1))
                draw.ellipse([lx - hr + scale, ey - eye_base_h * 0.5, lx + hr + scale, ey - eye_base_h * 0.5 + hr * 2], fill=(255, 255, 255, 220))
                draw.ellipse([rx - hr + scale, ey - eye_base_h * 0.5, rx + hr + scale, ey - eye_base_h * 0.5 + hr * 2], fill=(255, 255, 255, 220))

        composite = Image.alpha_composite(glow_blurred, img)
        return composite.resize((size, size), Image.Resampling.LANCZOS)

    def get_photo_image(self, size: int, mood: str, phase: float) -> ImageTk.PhotoImage:
        img = self.render_face(size=size, mood=mood, scale=3, phase=phase)
        photo = ImageTk.PhotoImage(img)
        if size <= 32:
            self._ref_compact = photo
        else:
            self._ref_expanded = photo
        return photo


def build_twocode_robo_face(size: int = 40, mood: str = "online", scale: int = 3) -> Image.Image:
    """Static fallback for TwoCode Robo mascot face."""
    mascot = WobnimoMascot()
    return mascot.render_face(size=size, mood=mood, scale=scale, phase=0.0)



def build_twocode_background(
    w: int,
    h: int,
    mood: str = "online",
    expanded: bool = False,
    scale: int = 1,
    style: str = "island",
    theme: str = "mac_glass"
) -> Image.Image:
    """Generate authentic React/iOS-inspired Frosted Glass card deck with sub-pixel antialiasing."""
    # 4x internal supersampling for pristine antialiasing and sub-pixel edge clarity
    ss = 4
    sw, sh = max(8, w * ss), max(8, h * ss)

    # Master canvas initialized with transparent colorkey (RGB 1, 1, 1)
    img = Image.new("RGBA", (sw, sh), (1, 1, 1, 255))
    draw = ImageDraw.Draw(img)

    if not expanded:
        # COMPACT MODE: Dynamic Island with Apple Intelligence Fluid Glow Aura
        pw = 220 * ss
        ph = 44 * ss
        cx1 = (sw - pw) // 2
        cy1 = 6 * ss
        cx2 = cx1 + pw
        cy2 = cy1 + ph
        radius = ph // 2

        # Apple Intelligence Fluid Glow Aura (Amber -> Rose -> Cyan)
        aura = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        adraw = ImageDraw.Draw(aura)
        aura_pad = 4 * ss
        for ax in range(cx1 - aura_pad, cx2 + aura_pad):
            t = (ax - (cx1 - aura_pad)) / max(1, (cx2 - cx1 + aura_pad * 2))
            if t < 0.5:
                kt = t / 0.5
                ar = int(251 + (244 - 251) * kt)
                ag = int(191 + (63 - 191) * kt)
                ab = int(36 + (94 - 36) * kt)
            else:
                kt = (t - 0.5) / 0.5
                ar = int(244 + (34 - 244) * kt)
                ag = int(63 + (211 - 63) * kt)
                ab = int(94 + (238 - 94) * kt)
            adraw.line([(ax, cy1 - aura_pad), (ax, cy2 + aura_pad)], fill=(ar, ag, ab, 70))

        aura_mask = Image.new("L", (sw, sh), 0)
        amdraw = ImageDraw.Draw(aura_mask)
        amdraw.rounded_rectangle([cx1 - aura_pad, cy1 - aura_pad, cx2 + aura_pad, cy2 + aura_pad], radius=radius + aura_pad, fill=255)
        aura.putalpha(Image.composite(aura.split()[3], Image.new("L", (sw, sh), 0), aura_mask))
        aura_blurred = aura.filter(ImageFilter.GaussianBlur(radius=6 * ss))
        img.paste(aura_blurred, (0, 0), aura_blurred)

        # Core Island Body: bg-black/85 backdrop-blur-2xl rounded-full border border-white/10
        island = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        isdraw = ImageDraw.Draw(island)
        for y in range(cy1, cy2):
            t = (y - cy1) / max(1, (cy2 - cy1) - 1)
            v = int(14 * (1.0 - t))
            isdraw.line([(cx1, y), (cx2, y)], fill=(8 + v, 10 + v, 15 + v, 255))

        imask = Image.new("L", (sw, sh), 0)
        imdraw = ImageDraw.Draw(imask)
        imdraw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=radius, fill=255)
        img.paste(island, (0, 0), imask)

        # 1px border border-white/10 & top gleam
        draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=radius, outline=(255, 255, 255, 36), width=ss)
        draw.line([(cx1 + radius, cy1 + ss), (cx2 - radius, cy1 + ss)], fill=(255, 255, 255, 90), width=ss)

    else:
        # EXPANDED MODE: Dynamic Island Pill at Top (y: 6->50) + iOS Card Deck (y: 60->340)
        # 1. Top Dynamic Island Pill
        pw = 220 * ss
        ph = 44 * ss
        px1 = (sw - pw) // 2
        py1 = 6 * ss
        px2 = px1 + pw
        py2 = py1 + ph
        pradius = ph // 2

        aura = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        adraw = ImageDraw.Draw(aura)
        aura_pad = 4 * ss
        for ax in range(px1 - aura_pad, px2 + aura_pad):
            t = (ax - (px1 - aura_pad)) / max(1, (px2 - px1 + aura_pad * 2))
            if t < 0.5:
                kt = t / 0.5
                ar = int(251 + (244 - 251) * kt)
                ag = int(191 + (63 - 191) * kt)
                ab = int(36 + (94 - 36) * kt)
            else:
                kt = (t - 0.5) / 0.5
                ar = int(244 + (34 - 244) * kt)
                ag = int(63 + (211 - 63) * kt)
                ab = int(94 + (238 - 94) * kt)
            adraw.line([(ax, py1 - aura_pad), (ax, py2 + aura_pad)], fill=(ar, ag, ab, 70))

        aura_mask = Image.new("L", (sw, sh), 0)
        amdraw = ImageDraw.Draw(aura_mask)
        amdraw.rounded_rectangle([px1 - aura_pad, py1 - aura_pad, px2 + aura_pad, py2 + aura_pad], radius=pradius + aura_pad, fill=255)
        aura.putalpha(Image.composite(aura.split()[3], Image.new("L", (sw, sh), 0), aura_mask))
        aura_blurred = aura.filter(ImageFilter.GaussianBlur(radius=6 * ss))
        img.paste(aura_blurred, (0, 0), aura_blurred)

        pill_surf = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pill_surf)
        for y in range(py1, py2):
            t = (y - py1) / max(1, (py2 - py1) - 1)
            v = int(14 * (1.0 - t))
            pdraw.line([(px1, y), (px2, y)], fill=(8 + v, 10 + v, 15 + v, 255))

        pmask = Image.new("L", (sw, sh), 0)
        pmdraw = ImageDraw.Draw(pmask)
        pmdraw.rounded_rectangle([px1, py1, px2, py2], radius=pradius, fill=255)
        img.paste(pill_surf, (0, 0), pmask)
        draw.rounded_rectangle([px1, py1, px2, py2], radius=pradius, outline=(255, 255, 255, 36), width=ss)
        draw.line([(px1 + pradius, py1 + ss), (px2 - pradius, py1 + ss)], fill=(255, 255, 255, 90), width=ss)

        # 2. Expanded 3-Card Deck Architecture
        deck_y = 60 * ss
        deck_h = 280 * ss
        deck_w = 760 * ss
        deck_x = (sw - deck_w) // 2

        left_w = 460 * ss
        lx1 = deck_x
        lx2 = lx1 + left_w
        ly1 = deck_y
        ly2 = ly1 + deck_h
        card_r = 24 * ss

        def draw_frosted_card(x1, y1, x2, y2, r, has_cyan_spot=False):
            ch = y2 - y1
            csurf = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            cdraw = ImageDraw.Draw(csurf)
            for y in range(y1, y2):
                t = (y - y1) / max(1, ch - 1)
                r_c = int(24 - 10 * t)
                g_c = int(30 - 12 * t)
                b_c = int(44 - 16 * t)
                cdraw.line([(x1, y), (x2, y)], fill=(r_c, g_c, b_c, 255))

            if has_cyan_spot:
                spot = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
                spdraw = ImageDraw.Draw(spot)
                spdraw.ellipse([x1 - 30 * ss, y1 - 30 * ss, x1 + 100 * ss, y1 + 100 * ss], fill=(6, 182, 212, 45))
                spot_blurred = spot.filter(ImageFilter.GaussianBlur(radius=25 * ss))
                csurf = Image.alpha_composite(csurf, spot_blurred)

            cmask = Image.new("L", (sw, sh), 0)
            cmdraw = ImageDraw.Draw(cmask)
            cmdraw.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=255)
            img.paste(csurf, (0, 0), cmask)

            draw.rounded_rectangle([x1, y1, x2, y2], radius=r, outline=(255, 255, 255, 28), width=ss)
            draw.line([(x1 + r, y1 + ss), (x2 - r, y1 + ss)], fill=(255, 255, 255, 75), width=ss)

        # Left Card (Assistant Intelligence Deck)
        draw_frosted_card(lx1, ly1, lx2, ly2, card_r, has_cyan_spot=True)

        # Right Cards Column
        gap = 10 * ss
        rx1 = lx2 + gap
        rx2 = deck_x + deck_w
        rc_h = (deck_h - gap) // 2

        # Right Card 1 (iOS Lockscreen Clock Card)
        draw_frosted_card(rx1, deck_y, rx2, deck_y + rc_h, 22 * ss)

        # Right Card 2 (iOS Battery & Hardware Telemetry Card)
        draw_frosted_card(rx1, deck_y + rc_h + gap, rx2, deck_y + deck_h, 22 * ss)

    # Downsample with high-fidelity Lanczos filter
    final_img = img.resize((w, h), Image.Resampling.LANCZOS)

    # Clean colorkey boundary: snap near-colorkey fringe pixels to exact (1, 1, 1)
    pixels = final_img.load()
    for py in range(h):
        for px in range(w):
            pr, pg, pb, _ = pixels[px, py]
            if pr < 10 and pg < 10 and pb < 10:
                pixels[px, py] = (1, 1, 1, 255)

    return final_img


def make_cubic_bezier(p1x: float, p1y: float, p2x: float, p2y: float):
    """Newton-Raphson 1D cubic-bezier easing solver."""
    def solve(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        s = t
        for _ in range(8):
            xs = 3.0 * (1.0 - s)**2 * s * p1x + 3.0 * (1.0 - s) * s**2 * p2x + s**3
            dx = 3.0 * (1.0 - s)**2 * p1x + 6.0 * (1.0 - s) * s * (p2x - p1x) + 3.0 * s**2 * (1.0 - p2x)
            if abs(dx) < 1e-6:
                break
            s -= (xs - t) / dx
            s = max(0.0, min(1.0, s))
        return 3.0 * (1.0 - s)**2 * s * p1y + 3.0 * (1.0 - s) * s**2 * p2y + s**3
    return solve


# Native Windows 11 Fluid Curve Easing Functions
EASE_EXPAND = make_cubic_bezier(0.1, 0.9, 0.2, 1.0)     # Fluid expansion curve
EASE_COLLAPSE = make_cubic_bezier(0.7, 0.0, 0.84, 0.0)   # Quick snap collapse curve


def _rounded_rect_points(x1: float, y1: float, x2: float, y2: float, r: float = 8.0) -> list[float]:
    r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


class JarvisIslandWidget:
    """Dynamic Island UI for Jarvis."""

    def __init__(self, asst: Assistant):
        self.asst = asst
        if hasattr(self.asst, "ctx"):
            self.asst.ctx.widget = self

        # Island Dimensions (Matches React iOS Dynamic Island & Card Architecture)
        self.W_COMPACT = 240
        self.W_COMPACT_WAVE = 240
        self.H_COMPACT = 56
        self.W_EXPANDED = 780
        self.H_EXPANDED = 360
        self.H_REPLY_EXTRA = 60

        # Fixed Window Container Dimensions
        self.WIN_W = 780
        self.WIN_H = 360

        self.expanded = False
        self.hover_expanded = False
        self.cur_w = float(self.W_COMPACT)
        self.cur_h = float(self.H_COMPACT)
        self.target_w = float(self.W_COMPACT)
        self.target_h = float(self.H_COMPACT)
        self._animating = False
        self._is_expanding = True

        # Euler Spring Physics Simulation (Signature organic Apple / Nixi bounce)
        # F = -k*(x - target) - c*v  (where k = 290.0, c = 26.0 gives damping ratio ~0.76)
        self.vel_w = 0.0
        self.vel_h = 0.0
        self.spring_k = 290.0
        self.spring_c = 26.0
        self._last_tick_time = time.perf_counter()

        # Dynamic Audio Waveform & Micro-Interactions
        self._smooth_audio_level = 0.0
        self._hover_chip: str | None = None

        # State
        self.status_label = "Ready"
        self.status_color = "#a3a3a3"
        self.last_query = ""
        self.last_reply = "Welcome back, sir. All systems nominal."
        self.is_listening = False
        self.is_thinking = False
        self.is_speaking = False
        self.current_tool_badge: str | None = None
        self.chip_approve_bbox: tuple[int, int, int, int] | None = None
        self.chip_deny_bbox: tuple[int, int, int, int] | None = None
        self._reset_timer_id = None
        self._active_speech_id = None
        self._collapse_timer_id = None
        self._ui_queue: queue.Queue = queue.Queue()

        # NotchPixel Visual Configuration & Modes
        self.island_style = os.environ.get("ISLAND_STYLE", "island").lower()  # "island" or "notch"
        self.theme = os.environ.get("ISLAND_THEME", "liquid_glass").lower()  # "liquid_glass" or "oled_black"

        # Media & System Sentinels
        self.hud_volume_active = False
        self.hud_volume_val = 50
        self.hud_volume_muted = False
        self.hud_volume_until = 0.0

        self.hud_mic_active = False
        self.hud_mic_muted = False
        self.hud_mic_until = 0.0

        self.media_state = media_controller.MediaState()
        self.media_sentinel = media_controller.get_media_sentinel(self._on_media_state_changed)
        self.sys_sentinel = system_sentinel.get_system_sentinel(on_vol=self._on_volume_changed, on_mic=self._on_mic_changed)

        self.telemetry = get_system_telemetry()
        self.telemetry_tick = 0
        self._bg_cache: dict[tuple[int, int, str, bool], ImageTk.PhotoImage] = {}

        # Telemetry & UI Animation Phase
        self._anim_phase = 0.0
        self._cur_cpu_pct = 20.0
        self._target_cpu_pct = 20.0
        self._cur_ram_pct = 50.0
        self._target_ram_pct = 50.0
        self._stream_words: list[str] | None = None
        self._stream_idx = 0
        try:
            self._target_cpu_pct = float(self.telemetry["cpu"].rstrip("%"))
            self._target_ram_pct = float(self.telemetry["ram"].rstrip("%"))
            self._cur_cpu_pct = self._target_cpu_pct
            self._cur_ram_pct = self._target_ram_pct
        except Exception:
            pass

        # Hook into speaker
        self._orig_speak = self.asst.speaker.speak
        self.asst.speaker.speak = self._on_speaker_text

        # Initialize Root Window (Fixed OS window container at top-center)
        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S. Island")

        # Set App Icon and Windows AppUserModelID
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("stark.jarvis.windows.island")
        except Exception:
            pass

        icon_path = HERE / "jarvis.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                try:
                    self.root.wm_iconbitmap(str(icon_path))
                except Exception:
                    pass
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.win_x = int((self.screen_w - self.WIN_W) / 2)
        self.win_y = 0

        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.configure(bg="#010101")
        try:
            self.root.wm_attributes("-transparentcolor", "#010101")
        except Exception:
            pass

        self._update_geometry()
        self.root.update_idletasks()

        # Windows 11 DWM Immersive Dark Mode
        try:
            import ctypes
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIN_W,
            height=self.WIN_H,
            bg="#010101",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Living Wobnimo Spring-Physics Mascot
        print("  [Island] Initializing Wobnimo spring-driven procedural 3D mascot...")
        self.mascot = WobnimoMascot()
        self._last_user_activity = time.perf_counter()
        self.robo_faces_compact: dict[str, ImageTk.PhotoImage] = {}
        self.robo_faces_expanded: dict[str, ImageTk.PhotoImage] = {}

        # Unified Chat Entry Frame (React iOS Card Deck Inset)
        self.input_frame = tk.Frame(self.canvas, bg="#141926")
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            self.input_frame,
            textvariable=self.entry_var,
            bg="#141926",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=8, pady=3)
        self.entry.bind("<Return>", lambda e: self.on_send())
        self.entry.bind("<FocusIn>", self._on_entry_focus_in)
        self.entry.bind("<FocusOut>", self._on_entry_focus_out)
        self._placeholder_active = True
        self._set_placeholder()

        # Scrollable Reply Area (React iOS Card Deck Bubble Inset)
        self.reply_frame = tk.Frame(self.canvas, bg="#0b0f1a")
        self.reply_text = tk.Text(
            self.reply_frame,
            bg="#0b0f1a",
            fg="#e2e8f0",
            font=("Segoe UI", 9),
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="arrow",
            selectbackground="#1e293b",
            selectforeground="#f8fafc"
        )
        self.reply_text.pack(fill="both", expand=True)
        self.reply_text.bind("<MouseWheel>", self._on_reply_scroll)
        self.reply_text.bind("<Button-4>", lambda e: self.reply_text.yview_scroll(-2, "units"))
        self.reply_text.bind("<Button-5>", lambda e: self.reply_text.yview_scroll(2, "units"))
        self.reply_text.bind("<Button-1>", self._on_reply_click)
        self._last_rendered_reply = None

        # Fonts for dynamic metrics (Matching React iOS Deck Design)
        self.font_chip_bold = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.font_chip_norm = tkfont.Font(family="Segoe UI", size=8)
        self.font_clock = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        self.font_clock_date = tkfont.Font(family="Segoe UI", size=8)
        self.font_compact_title = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.font_compact_status = tkfont.Font(family="Segoe UI", size=8)
        self.font_section_lbl = tkfont.Font(family="Segoe UI", size=7, weight="bold")

        # Canvas items
        self._init_canvas_items()

        # Event bindings
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Enter>", self._on_mouse_enter)
        self.canvas.bind("<Leave>", self._on_mouse_leave)
        self.canvas.bind("<Motion>", self._on_mouse_motion)
        self.canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.root.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<Key>", self._on_key_redirect)
        self.canvas.bind("<Key>", self._on_key_redirect)

        # Geometry & 60 FPS animation loop
        self._update_geometry()
        self.root.after(16, self._anim_loop)
        self._init_hotkeys()

        # Check for first daily run to prompt for morning briefing
        self.root.after(1200, self._check_first_daily_run)

    def _truncate_text_to_width(self, text: str, font: tkfont.Font, max_width_px: int) -> str:
        """Safely truncate text with ellipsis if it exceeds max_width_px."""
        if not text:
            return ""
        try:
            if font.measure(text) <= max_width_px:
                return text
            ell = "…"
            ell_w = font.measure(ell)
            if ell_w >= max_width_px:
                return ""
            cur = text
            while cur and (font.measure(cur + ell) > max_width_px):
                cur = cur[:-1]
            return (cur + ell) if cur else ell
        except Exception:
            return text[:12]

    def _init_canvas_items(self):
        # 1. Background image
        self.item_bg = self.canvas.create_image(0, 0, anchor="nw")

        # 2. Compact Dynamic Island (Apple Intelligence Aura & Siri Multi-Color Waveform)
        self.item_compact_robo = self.canvas.create_image(0, 0, tags="btn_notch")
        self.item_compact_title = self.canvas.create_text(0, 0, anchor="w", text="J.A.R.V.I.S.", font=self.font_compact_title, fill="#ffffff", state="hidden", tags="btn_notch")
        self.item_compact_status = self.canvas.create_text(0, 0, anchor="w", text="Ready", font=self.font_compact_status, fill="#94a3b8", state="hidden", tags="btn_notch")
        self.item_compact_div = self.canvas.create_line(0, 0, 0, 0, fill="#334155", state="hidden", tags="btn_notch")
        self.item_compact_chevron = self.canvas.create_text(0, 0, text="⤢", font=("Segoe UI", 8), fill="#64748b", state="hidden", tags="btn_notch")
        self.item_wave_bar1 = self.canvas.create_polygon(0, 0, 0, 0, fill="#22d3ee", state="hidden", tags="btn_notch")
        self.item_wave_bar2 = self.canvas.create_polygon(0, 0, 0, 0, fill="#818cf8", state="hidden", tags="btn_notch")
        self.item_wave_bar3 = self.canvas.create_polygon(0, 0, 0, 0, fill="#fb7185", state="hidden", tags="btn_notch")
        self.item_wave_bar4 = self.canvas.create_polygon(0, 0, 0, 0, fill="#22d3ee", state="hidden", tags="btn_notch")
        self.canvas.tag_bind("btn_notch", "<Button-1>", lambda e: (self.mascot.trigger_click_wobble(), self.toggle_expand(True)))

        # Waveform Equalizer Bars for Expanded Mode (Top-Right of AI Assistant Card)
        self.exp_wave_bar1 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden")
        self.exp_wave_bar2 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden")
        self.exp_wave_bar3 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden")
        self.exp_wave_bar4 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden")
        self.exp_wave_bar5 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden")

        # 3. Top Header Bar (Expanded Mode)
        self.item_header_logo = self.canvas.create_text(18, 15, anchor="w", text="J.A.R.V.I.S.", font=("Segoe UI", 8, "bold"), fill="#94a3b8", state="hidden")
        self.item_btn_min = self.canvas.create_text(0, 0, text="—", font=("Segoe UI", 9, "bold"), fill="#94a3b8", tags="btn_min", state="hidden")
        self.item_btn_close = self.canvas.create_text(0, 0, text="✕", font=("Segoe UI", 8, "bold"), fill="#94a3b8", tags="btn_close", state="hidden")

        # 4. Left AI Assistant Card (React iOS Deck)
        self.item_agent_robo = self.canvas.create_image(0, 0, tags="btn_robo", state="hidden")
        self.canvas.tag_bind("btn_robo", "<Button-1>", lambda e: self.mascot.trigger_click_wobble())
        self.item_agent_title = self.canvas.create_text(0, 0, anchor="w", text="Assistant Intelligence", font=("Segoe UI", 10, "bold"), fill="#ffffff", state="hidden")
        self.item_agent_sub = self.canvas.create_text(0, 0, anchor="w", text="NEURAL LINK // ACTIVE", font=self.font_section_lbl, fill="#64748b", state="hidden")
        self.item_agent_status = self.canvas.create_text(0, 0, anchor="w", text="● Ready", font=("Segoe UI", 8), fill="#94a3b8", state="hidden")
        self.item_agent_badge_bg = self.canvas.create_polygon(0, 0, 0, 0, fill="#064e3b", outline="#059669", width=1.0, smooth=True, state="hidden")
        self.item_agent_badge = self.canvas.create_text(0, 0, text="Optimal", font=self.font_chip_bold, fill="#34d399", state="hidden")

        # Input Box Outline & Icons
        self.item_input_box = self.canvas.create_polygon(0, 0, 0, 0, fill="#141926", outline="#333f5c", width=1.0, smooth=True, state="hidden")
        self.item_btn_send_bg = self.canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline="", tags="btn_send", state="hidden")
        self.item_btn_send = self.canvas.create_text(0, 0, text="➤", font=("Segoe UI", 8, "bold"), fill="#000000", tags="btn_send", state="hidden")
        self.item_btn_mic_bg = self.canvas.create_oval(0, 0, 0, 0, fill="#1e2538", outline="#334155", width=1.0, tags="btn_mic", state="hidden")
        self.item_btn_mic = self.canvas.create_text(0, 0, text="🎙", font=("Segoe UI", 9), fill="#f8fafc", tags="btn_mic", state="hidden")

        # Reply & Output Text
        self.item_reply_text = self.canvas.create_text(0, 0, anchor="nw", text="", font=("Segoe UI", 9), fill="#e2e8f0", state="hidden")

        # Interactive Action / Approval Chips (Yes / No)
        self.item_chip_approve_bg = self.canvas.create_polygon(0, 0, 0, 0, fill="#065f46", outline="#34d399", width=1.0, smooth=True, state="hidden", tags="chip_approve")
        self.item_chip_approve_text = self.canvas.create_text(0, 0, text="✓ Yes", font=("Segoe UI", 8, "bold"), fill="#f8fafc", state="hidden", tags="chip_approve")
        self.item_chip_deny_bg = self.canvas.create_polygon(0, 0, 0, 0, fill="#1e2433", outline="#475569", width=1.0, smooth=True, state="hidden", tags="chip_deny")
        self.item_chip_deny_text = self.canvas.create_text(0, 0, text="✕ No", font=("Segoe UI", 8), fill="#94a3b8", state="hidden", tags="chip_deny")

        # 5. Right Top Card: iOS Lockscreen-Style Clock Card
        self.item_clock_hdr = self.canvas.create_text(0, 0, anchor="nw", text="CLOCK", font=self.font_section_lbl, fill="#64748b", state="hidden")
        self.item_clock_icon = self.canvas.create_text(0, 0, text="🔊", font=("Segoe UI", 8), fill="#64748b", state="hidden")
        self.item_clock_time = self.canvas.create_text(0, 0, anchor="nw", text="12", font=self.font_clock, fill="#ffffff", state="hidden")
        self.item_clock_colon = self.canvas.create_text(0, 0, anchor="nw", text=":", font=self.font_clock, fill="#ffffff", state="hidden")
        self.item_clock_mm = self.canvas.create_text(0, 0, anchor="nw", text="00", font=self.font_clock, fill="#ffffff", state="hidden")
        self.item_clock_date = self.canvas.create_text(0, 0, anchor="nw", text="Mon 02 Nov", font=self.font_clock_date, fill="#94a3b8", state="hidden")
        self.item_clock_div = self.canvas.create_line(0, 0, 0, 0, fill="#1e293b", state="hidden")
        self.item_clock_footer = self.canvas.create_text(0, 0, anchor="nw", text="System Time Synced", font=self.font_chip_bold, fill="#22d3ee", state="hidden")

        # 6. Right Bottom Card: iOS Battery & Hardware Telemetry Card
        self.item_bat_badge = self.canvas.create_polygon(0, 0, 0, 0, fill="#064e3b", outline="#059669", width=1.0, smooth=True, state="hidden")
        self.item_bolt_glow = self.canvas.create_polygon(0, 0, 0, 0, fill="#14532d", state="hidden")
        self.item_bolt = self.canvas.create_polygon(0, 0, 0, 0, fill="#4ade80", state="hidden")
        self.item_sys_bat = self.canvas.create_text(0, 0, anchor="nw", text="Battery", font=("Segoe UI", 9, "bold"), fill="#f8fafc", state="hidden")
        self.item_bat_tag = self.canvas.create_text(0, 0, anchor="e", text="FAST", font=self.font_section_lbl, fill="#34d399", state="hidden")

        self.item_cpu_lbl = self.canvas.create_text(0, 0, anchor="nw", text="CPU 12%", font=("Segoe UI", 8), fill="#94a3b8", state="hidden")
        self.item_cpu_track = self.canvas.create_polygon(0, 0, 0, 0, fill="#1e2433", state="hidden")
        self.item_cpu_fill = self.canvas.create_polygon(0, 0, 0, 0, fill="#38bdf8", state="hidden")

        self.item_ram_lbl = self.canvas.create_text(0, 0, anchor="nw", text="RAM 48%", font=("Segoe UI", 8), fill="#94a3b8", state="hidden")
        self.item_ram_track = self.canvas.create_polygon(0, 0, 0, 0, fill="#1e2433", state="hidden")
        self.item_ram_fill = self.canvas.create_polygon(0, 0, 0, 0, fill="#f59e0b", state="hidden")

        # 7. NotchPixel Enhancements:
        # A. Compact HUD (Volume & Mic Mute)
        self.item_hud_icon = self.canvas.create_text(0, 0, text="", font=("Segoe UI", 10), fill="#f5f5f5", state="hidden")
        self.item_hud_text = self.canvas.create_text(0, 0, anchor="w", text="", font=self.font_compact_title, fill="#f5f5f5", state="hidden")
        self.item_hud_sub = self.canvas.create_text(0, 0, anchor="w", text="", font=self.font_compact_status, fill="#a3a3a3", state="hidden")
        self.item_hud_track = self.canvas.create_polygon(0, 0, 0, 0, fill="#262626", state="hidden")
        self.item_hud_fill = self.canvas.create_polygon(0, 0, 0, 0, fill="#38bdf8", state="hidden")

        # B. Compact Media (Now Playing vinyl record, song title, and animated equalizer)
        self.item_media_disc = self.canvas.create_oval(0, 0, 0, 0, fill="#1db954", outline="#1ed760", width=1, state="hidden")
        self.item_media_hole = self.canvas.create_oval(0, 0, 0, 0, fill="#0c0e14", outline="", state="hidden")
        self.item_media_title = self.canvas.create_text(0, 0, anchor="w", text="", font=self.font_compact_title, fill="#f5f5f5", state="hidden")
        self.item_media_artist = self.canvas.create_text(0, 0, anchor="w", text="", font=self.font_compact_status, fill="#1db954", state="hidden")
        self.item_media_bar1 = self.canvas.create_polygon(0, 0, 0, 0, fill="#1db954", state="hidden")
        self.item_media_bar2 = self.canvas.create_polygon(0, 0, 0, 0, fill="#1db954", state="hidden")
        self.item_media_bar3 = self.canvas.create_polygon(0, 0, 0, 0, fill="#1db954", state="hidden")
        self.item_media_bar4 = self.canvas.create_polygon(0, 0, 0, 0, fill="#1db954", state="hidden")

        # C. Compact Mic Sentinel persistent indicator dot
        self.item_mic_indicator = self.canvas.create_oval(0, 0, 0, 0, fill="#ef4444", outline="#7f1d1d", width=1, state="hidden")

        # D. Header Style Toggle button (Island vs Notch)
        self.item_btn_style_toggle = self.canvas.create_text(0, 0, text="🏝️", font=("Segoe UI", 9), fill="#737373", tags="btn_style", state="hidden")
        self.canvas.tag_bind("btn_style", "<Button-1>", lambda e: self.toggle_island_style())

        # E. Expanded Media Card Items (In Right Card 1 when media is playing)
        self.item_mc_badge = self.canvas.create_text(0, 0, anchor="nw", text="NOW PLAYING", font=("Segoe UI", 8, "bold"), fill="#1db954", state="hidden")
        self.item_mc_title = self.canvas.create_text(0, 0, anchor="nw", text="", font=("Segoe UI", 10, "bold"), fill="#f5f5f5", state="hidden")
        self.item_mc_artist = self.canvas.create_text(0, 0, anchor="nw", text="", font=("Segoe UI", 8), fill="#a3a3a3", state="hidden")
        self.item_mc_prev = self.canvas.create_text(0, 0, text="⏮", font=("Segoe UI", 11), fill="#d4d4d4", tags="mc_prev", state="hidden")
        self.item_mc_play = self.canvas.create_text(0, 0, text="▶", font=("Segoe UI", 12), fill="#f5f5f5", tags="mc_play", state="hidden")
        self.item_mc_next = self.canvas.create_text(0, 0, text="⏭", font=("Segoe UI", 11), fill="#d4d4d4", tags="mc_next", state="hidden")
        self.canvas.tag_bind("mc_prev", "<Button-1>", lambda e: self._on_media_prev())
        self.canvas.tag_bind("mc_play", "<Button-1>", lambda e: self._on_media_toggle())
        self.canvas.tag_bind("mc_next", "<Button-1>", lambda e: self._on_media_next())

    def _set_placeholder(self):
        self.entry_var.set("Ask Jarvis anything...")
        self.entry.config(fg="#64748b")
        self._placeholder_active = True

    def _on_entry_focus_in(self, event):
        self._cancel_collapse_timer()
        if hasattr(self, "_reset_timer_id") and self._reset_timer_id is not None:
            try:
                self.root.after_cancel(self._reset_timer_id)
            except Exception:
                pass
            self._reset_timer_id = None
        self.hover_expanded = False
        if self._placeholder_active:
            self.entry_var.set("")
            self.entry.config(fg="#f8fafc")
            self._placeholder_active = False

    def _on_entry_focus_out(self, event):
        if not self.entry_var.get().strip():
            self._set_placeholder()

    def _get_bg_photo(self, w: int, h: int, mood: str, expanded: bool) -> ImageTk.PhotoImage:
        key = (w, h, mood, expanded, getattr(self, "island_style", "island"), getattr(self, "theme", "liquid_glass"))
        photo = self._bg_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(build_twocode_background(
                w, h, mood, expanded,
                style=getattr(self, "island_style", "island"),
                theme=getattr(self, "theme", "liquid_glass")
            ))
            if len(self._bg_cache) > 200:
                self._bg_cache.clear()
            self._bg_cache[key] = photo
        return photo

    def _check_first_daily_run(self):
        if hasattr(self.asst, "check_daily_briefing_prompt"):
            threading.Thread(target=self.asst.check_daily_briefing_prompt, daemon=True).start()

    def _post_ui(self, fn):
        self._ui_queue.put(fn)

    def _process_ui_queue(self):
        while True:
            try:
                fn = self._ui_queue.get_nowait()
                fn()
            except queue.Empty:
                break
            except Exception as e:
                pass

    def _on_speaker_text(self, text: str, *args, **kwargs):
        speech_id = time.time()
        self._post_ui(lambda: self._start_speaking(text, speech_id))
        t_start = time.perf_counter()
        try:
            clean_text = str(text or "").strip()
            self._orig_speak(clean_text, *args, **kwargs)
        finally:
            dur = time.perf_counter() - t_start
            self._post_ui(lambda: self._on_speaking_finished(speech_id, dur))

    def _start_speaking(self, text: str, speech_id: float):
        if hasattr(self, "_reset_timer_id") and self._reset_timer_id is not None:
            try:
                self.root.after_cancel(self._reset_timer_id)
            except Exception:
                pass
            self._reset_timer_id = None

        self._active_speech_id = speech_id
        self.is_listening = False
        self.last_reply = str(text or "")
        self.status_label = "Speaking"
        self.status_color = "#10b981"
        self.is_speaking = True
        self.is_thinking = False
        # If in compact pill mode, stay compact: pill will smoothly spring open to 176px to reveal the audio waveform!
        self._recompute_target_size()

    def _on_speaking_finished(self, speech_id: float, duration: float):
        if getattr(self, "_active_speech_id", None) != speech_id:
            return
        self.is_speaking = False
        self.is_listening = False
        self.status_label = "Ready"
        self.status_color = "#a3a3a3"
        self._recompute_target_size()
        # Collapse to pill after response has finished speaking out
        self._reset_timer_id = self.root.after(1500, lambda: self._revert_after_speech(speech_id))

    def _revert_after_speech(self, speech_id: float):
        if getattr(self, "_active_speech_id", None) != speech_id:
            return
        self._reset_timer_id = None
        self.is_listening = False
        self.is_speaking = False
        self.temp_expanded_for_speech = False

        # Don't auto-collapse if user is actively speaking or another query is running
        if self.is_listening or self.is_thinking or self.is_speaking:
            return

        # Don't auto-collapse if user is actively typing a command in the input box
        if not getattr(self, "_placeholder_active", True) and self.entry_var.get().strip():
            return

        # Don't auto-collapse if interactive approval chip (Yes / No) is awaiting user confirmation
        has_approval = bool(getattr(self.asst, "pending_briefing", False) or getattr(self.asst, "pending_url", None))
        if has_approval:
            return

        # Collapse back to compact pill after 2 seconds
        if self.expanded:
            self.toggle_expand(False)
        self._reset_status()

    def _reset_status(self):
        self.is_listening = False
        self.is_speaking = False
        self.is_thinking = False
        self.status_label = "Ready"
        self.status_color = "#a3a3a3"
        self._recompute_target_size()

    def _start_transition(self, target_w: float, target_h: float, is_expanding: bool | None = None):
        if abs(self.cur_w - target_w) < 0.5 and abs(self.cur_h - target_h) < 0.5 and abs(self.vel_w) < 1.0 and abs(self.vel_h) < 1.0:
            self.cur_w = target_w
            self.cur_h = target_h
            self.target_w = target_w
            self.target_h = target_h
            self.vel_w = 0.0
            self.vel_h = 0.0
            self._animating = False
            return
        self.target_w = target_w
        self.target_h = target_h
        self._is_expanding = (target_w > self.cur_w) if is_expanding is None else is_expanding
        self._animating = True
        self._last_tick_time = time.perf_counter()

    def _recompute_target_size(self):
        if not self.expanded:
            tw = float(self.W_COMPACT)
            th = float(self.H_COMPACT)
            expanding = False
        else:
            tw = float(self.W_EXPANDED)
            th = float(self.H_EXPANDED)
            expanding = True

        self.target_w = tw
        self.target_h = th
        self.cur_w = tw
        self.cur_h = th
        self._animating = False

    def _cancel_collapse_timer(self):
        if getattr(self, "_collapse_timer_id", None) is not None:
            try:
                self.root.after_cancel(self._collapse_timer_id)
            except Exception:
                pass
            self._collapse_timer_id = None

    def _on_mouse_enter(self, event=None):
        self._cancel_collapse_timer()
        if not self.expanded:
            if event is not None and hasattr(event, "x") and hasattr(event, "y"):
                w = int(self.cur_w)
                h = int(self.cur_h)
                island_x = (self.WIN_W - w) // 2
                if not (island_x <= event.x <= island_x + w and 0 <= event.y <= h):
                    return
            self.hover_expanded = True
            self.toggle_expand(True)

    def _on_mouse_leave(self, event=None):
        if self.expanded:
            self._cancel_collapse_timer()
            self._collapse_timer_id = self.root.after(5000, self._check_hover_collapse)

    def _check_hover_collapse(self):
        self._collapse_timer_id = None
        if not self.expanded:
            return
        if self.is_speaking or self.is_listening or self.is_thinking:
            return
        if not self._placeholder_active and self.entry_var.get().strip():
            return
        try:
            if self.root.focus_get() == self.entry:
                return
        except Exception:
            pass
        try:
            rx = self.root.winfo_pointerx()
            ry = self.root.winfo_pointery()
            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            island_x = (self.WIN_W - int(self.cur_w)) // 2
            island_w = int(self.cur_w)
            island_h = int(self.cur_h)

            cur_x_in_win = rx - wx
            cur_y_in_win = ry - wy
            if island_x <= cur_x_in_win <= island_x + island_w and 0 <= cur_y_in_win <= island_h:
                return
        except Exception:
            pass
        self.hover_expanded = False
        self.toggle_expand(False)

    def _on_mouse_motion(self, event):
        self._cancel_collapse_timer()
        x, y = event.x, event.y
        w = int(self.cur_w)
        island_x = (self.WIN_W - w) // 2
        is_clickable = False
        if not self.expanded:
            if island_x <= x <= island_x + w and 0 <= y <= int(self.cur_h):
                is_clickable = True
                if not self.hover_expanded:
                    self.hover_expanded = True
                    self.toggle_expand(True)
        else:
            min_coords = self.canvas.coords(self.item_btn_min) if hasattr(self, "item_btn_min") else None
            close_coords = self.canvas.coords(self.item_btn_close) if hasattr(self, "item_btn_close") else None
            is_min = min_coords and (abs(x - min_coords[0]) <= 14) and (abs(y - min_coords[1]) <= 14)
            is_close = close_coords and (abs(x - close_coords[0]) <= 14) and (abs(y - close_coords[1]) <= 14)
            is_mic = hasattr(self, "_btn_mic_cx") and hasattr(self, "_btn_mic_cy") and (x - self._btn_mic_cx) ** 2 + (y - self._btn_mic_cy) ** 2 <= 16 ** 2
            is_send = hasattr(self, "_btn_send_cx") and hasattr(self, "_btn_send_cy") and (x - self._btn_send_cx) ** 2 + (y - self._btn_send_cy) ** 2 <= 16 ** 2
            if is_min or is_close or is_mic or is_send:
                is_clickable = True
                self._hover_chip = None
            elif self.chip_approve_bbox and (self.chip_approve_bbox[0] <= x <= self.chip_approve_bbox[2] and self.chip_approve_bbox[1] <= y <= self.chip_approve_bbox[3]):
                is_clickable = True
                self._hover_chip = "approve"
            elif self.chip_deny_bbox and (self.chip_deny_bbox[0] <= x <= self.chip_deny_bbox[2] and self.chip_deny_bbox[1] <= y <= self.chip_deny_bbox[3]):
                is_clickable = True
                self._hover_chip = "deny"
            else:
                self._hover_chip = None
        self.canvas.config(cursor="hand2" if is_clickable else "")

    def set_tool_badge(self, name: str | None):
        friendly_map = {
            # Email
            "read_and_summarize_email": "📬 Email",
            "search_email": "📬 Search Mail",
            "search_emails": "📬 Search Mail",
            "read_recent_emails": "📬 Email",
            "read_email_content": "📬 Email",
            "open_email_link": "🔗 Email Link",
            "email_summary": "📬 Inbox",
            # Web & Research
            "web_search": "🌐 Search",
            "browse_web_page": "🌐 Reading",
            "browse_page": "⚡ Lightpanda",
            "read_web_page": "🌐 Reading",
            "deep_research": "🔬 Research",
            "research": "🔬 Research",
            # Vision & Screen
            "screen_vision": "👁️ Vision",
            "look_at_screen": "👁️ Vision",
            "analyze_screen": "👁️ Vision",
            # System & Hardware
            "optimize_memory": "⚡ Memory",
            "clean_memory": "⚡ Memory",
            "free_memory": "⚡ Memory",
            "get_battery_status": "🔋 Battery",
            "battery_status": "🔋 Battery",
            "get_system_stats": "📊 System",
            "system_stats": "📊 System",
            "system_control": "⚙️ System",
            "control_volume": "🔊 Volume",
            "set_timer": "⏱️ Timer",
            "get_time_date": "🕒 Time",
            "manage_autostart": "⚡ Auto-Boot",
            "autostart": "⚡ Auto-Boot",
            "toggle_autostart": "⚡ Auto-Boot",
            # Apps & Media
            "open_app": "🚀 App",
            "close_app": "✕ Close",
            "open_website": "🌐 Website",
            "open_folder": "📂 Folder",
            "create_folder": "📁 Folder",
            "play_youtube_video": "▶️ YouTube",
            "youtube_summary": "📺 YouTube",
            "summarize_youtube_video": "📺 YouTube",
            "summarize_video": "📺 YouTube",
            "media_control": "🎵 Media",
            # Productivity
            "clipboard_action": "📋 Clipboard",
            "clipboard": "📋 Clipboard",
            "daily_digest": "🌅 Briefing",
            "get_daily_digest": "🌅 Briefing",
            "get_weather": "☀️ Weather",
            "weather": "☀️ Weather",
            "get_calendar_events": "📅 Calendar",
            "calendar": "📅 Calendar",
            "get_calendar": "📅 Calendar",
            "get_tasks": "📋 Tasks",
            "list_tasks": "📋 Tasks",
            "add_task": "📋 Task",
            "create_task": "📋 Task",
        }
        if name:
            if name in friendly_map:
                friendly = friendly_map[name]
            else:
                clean_name = name.replace("_", " ").strip().title()
                if len(clean_name) > 13:
                    clean_name = clean_name[:12].rstrip() + "…"
                friendly = f"⚙️ {clean_name}"
        else:
            friendly = None
        self._post_ui(lambda: self._set_tool_badge_ui(friendly))

    def _set_tool_badge_ui(self, badge_text: str | None):
        was_working = bool(self.current_tool_badge)
        self.current_tool_badge = badge_text
        if badge_text:
            self.status_label = "Working"
            self.status_color = "#f59e0b"
            self.is_thinking = True
        elif not self.is_speaking and not self.is_listening:
            self.status_label = "Ready"
            self.status_color = "#a3a3a3"
            self.is_thinking = False
            if was_working:
                self.mascot.trigger_celebrate(2.2)
        self._recompute_target_size()

    def _on_approve_click(self):
        self.chip_approve_bbox = None
        self.chip_deny_bbox = None
        if hasattr(self.asst, "speaker") and self.asst.speaker:
            self.asst.speaker.stop()
        self.is_speaking = False
        self._handle_voice_text("yes")

    def _on_deny_click(self):
        self.chip_approve_bbox = None
        self.chip_deny_bbox = None
        if hasattr(self.asst, "speaker") and self.asst.speaker:
            self.asst.speaker.stop()
        self.is_speaking = False
        self._handle_voice_text("no")

    def _on_key_redirect(self, event):
        if not self.expanded:
            return
        if event.widget == self.entry:
            return
        if self._placeholder_active:
            self.entry_var.set("")
            self.entry.config(fg="#f5f5f5")
            self._placeholder_active = False

        if event.keysym == "Return":
            self.on_send()
            return
        if event.keysym == "BackSpace":
            txt = self.entry_var.get()
            if txt:
                self.entry_var.set(txt[:-1])
                self.entry.icursor(tk.END)
            return
        if event.char and event.char.isprintable():
            self.entry.focus_force()
            self.entry.insert(tk.END, event.char)
            self.entry.icursor(tk.END)

    def keep_on_top(self, activate: bool = False):
        try:
            self.root.lift()
            self.root.wm_attributes("-topmost", True)
            if sys.platform == "win32":
                import ctypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                try:
                    top_hwnd = int(self.root.wm_frame(), 16)
                except Exception:
                    hwnd = self.root.winfo_id()
                    top_hwnd = user32.GetAncestor(hwnd, 2) or user32.GetParent(hwnd) or hwnd

                flags = 0x0002 | 0x0001 | 0x0040  # SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                if not activate:
                    flags |= 0x0010  # SWP_NOACTIVATE
                user32.SetWindowPos(top_hwnd, -1, 0, 0, 0, 0, flags)

                if activate:
                    fore_hwnd = user32.GetForegroundWindow()
                    app_tid = kernel32.GetCurrentThreadId()
                    fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0

                    if fore_tid != 0 and fore_tid != app_tid:
                        user32.AttachThreadInput(fore_tid, app_tid, True)

                    # Release modifier keys and tap Alt to unlock Windows foreground lock
                    user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt UP
                    user32.keybd_event(0x11, 0, 0x0002, 0)  # Ctrl UP
                    user32.keybd_event(0x10, 0, 0x0002, 0)  # Shift UP

                    user32.keybd_event(0x12, 0, 0, 0)       # Alt DOWN
                    user32.keybd_event(0x12, 0, 0x0002, 0)  # Alt UP

                    user32.BringWindowToTop(top_hwnd)
                    user32.ShowWindow(top_hwnd, 5)          # SW_SHOW
                    user32.SetForegroundWindow(top_hwnd)

                    if fore_tid != 0 and fore_tid != app_tid:
                        user32.AttachThreadInput(fore_tid, app_tid, False)

                    user32.SetFocus(top_hwnd)
        except Exception:
            pass

    def focus_input(self):
        if not self.expanded:
            return
        if self._placeholder_active:
            self.entry_var.set("")
            self.entry.config(fg="#f5f5f5")
            self._placeholder_active = False

        # Place input_frame exactly inside the iOS prompt pill bar
        # Left card: x: 10 -> 470, y: 60 -> 340, pill bar: input_y = 294, input_h = 32
        self.input_frame.place(x=40, y=298, width=344, height=24)

        self.keep_on_top(activate=True)
        self.root.lift()
        self.entry.focus_force()
        self.entry.icursor(tk.END)

    def toggle_island_style(self):
        """Toggle between Floating Island capsule and Top Hanging Notch mode."""
        self.island_style = "notch" if self.island_style == "island" else "island"
        self._bg_cache.clear()
        self._recompute_target_size()
        print(f"  [Island] Mode switched to: {self.island_style.upper()}")

    def toggle_mic_mute(self):
        """Universal Global Microphone Mute sentinel toggle."""
        if hasattr(self, "sys_sentinel") and self.sys_sentinel:
            muted = self.sys_sentinel.toggle_mic_mute()
            self._show_mic_hud(muted)

    def _show_mic_hud(self, muted: bool):
        self.hud_mic_active = True
        self.hud_mic_muted = muted
        self.hud_mic_until = time.perf_counter() + 2.0
        self._recompute_target_size()

    def _on_mic_changed(self, muted: bool):
        self._post_ui(lambda: self._show_mic_hud(muted))

    def _on_volume_changed(self, vol: int, muted: bool):
        self._post_ui(lambda: self._show_volume_hud(vol, muted))

    def _show_volume_hud(self, vol: int, muted: bool):
        self.hud_volume_active = True
        self.hud_volume_val = vol
        self.hud_volume_muted = muted
        self.hud_volume_until = time.perf_counter() + 1.8
        self._recompute_target_size()

    def _on_media_state_changed(self, state: media_controller.MediaState):
        self._post_ui(lambda: self._apply_media_state(state))

    def _apply_media_state(self, state: media_controller.MediaState):
        self.media_state = state
        self._recompute_target_size()

    def _on_media_prev(self):
        if hasattr(self, "media_sentinel") and self.media_sentinel:
            self.media_sentinel.prev_track()

    def _on_media_toggle(self):
        if hasattr(self, "media_sentinel") and self.media_sentinel:
            self.media_sentinel.toggle_play_pause()

    def _on_media_next(self):
        if hasattr(self, "media_sentinel") and self.media_sentinel:
            self.media_sentinel.next_track()

    def _init_hotkeys(self):
        try:
            import keyboard
            keyboard.add_hotkey("ctrl+space", lambda: self._post_ui(self._handle_hotkey), suppress=True)
            keyboard.add_hotkey("alt+space", lambda: self._post_ui(self._handle_hotkey), suppress=True)
            keyboard.add_hotkey("ctrl+shift+j", lambda: self._post_ui(self._handle_hotkey), suppress=True)
            keyboard.add_hotkey("ctrl+alt+m", lambda: self._post_ui(self.toggle_mic_mute), suppress=True)
            keyboard.add_hotkey("ctrl+alt+n", lambda: self._post_ui(self.toggle_island_style), suppress=True)
            print("  [Island] Global hotkeys active: ctrl+space, alt+space, ctrl+shift+j, ctrl+alt+m (Mic Mute), ctrl+alt+n (Island/Notch)")
        except Exception as e:
            pass

    def _handle_hotkey(self):
        self.hover_expanded = False
        if not self.expanded:
            self.toggle_expand(True)
        else:
            try:
                if self.root.focus_get() == self.entry:
                    self.toggle_expand(False)
                else:
                    self.focus_input()
            except Exception:
                self.toggle_expand(False)

    def _on_escape(self, event=None):
        self.hover_expanded = False
        if getattr(self, "is_speaking", False):
            if hasattr(self.asst, "speaker") and self.asst.speaker:
                self.asst.speaker.stop()
            self.is_speaking = False
            self._reset_status()
        else:
            self.toggle_expand(False)

    def toggle_expand(self, force_state: bool | None = None):
        self._cancel_collapse_timer()
        if force_state is not None:
            self.expanded = force_state
        else:
            self.expanded = not self.expanded

        self._update_geometry()
        self._recompute_target_size()
        if self.expanded:
            self.root.deiconify()
            self.focus_input()
            # Staged activation guarantees immediate typing across any foreground window
            self.root.after(20, self.focus_input)
            self.root.after(80, self.focus_input)
            self.root.after(180, self.focus_input)
        else:
            self.hover_expanded = False
            self.input_frame.place_forget()
            if hasattr(self, "reply_frame"):
                self.reply_frame.place_forget()
            self.keep_on_top(activate=False)

    def _on_reply_scroll(self, event):
        self._finish_reply_stream()
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta != 0:
            self.reply_text.yview_scroll(delta * 2, "units")
        return "break"

    def _on_canvas_mousewheel(self, event):
        if self.expanded and hasattr(self, "reply_text"):
            self._finish_reply_stream()
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            if delta != 0:
                self.reply_text.yview_scroll(delta * 2, "units")

    def _on_reply_click(self, event=None):
        self._finish_reply_stream()
        self._cancel_collapse_timer()
        self.hover_expanded = False
        if getattr(self, "is_speaking", False):
            if hasattr(self.asst, "speaker") and self.asst.speaker:
                self.asst.speaker.stop()
            self.is_speaking = False
            self._reset_status()

    def _finish_reply_stream(self):
        if getattr(self, "_stream_words", None):
            full_text = " ".join(self._stream_words)
            self._stream_words = None
            self.reply_text.config(state="normal")
            self.reply_text.delete("1.0", tk.END)
            self.reply_text.insert("1.0", full_text)
            self.reply_text.config(state="disabled")

    def _update_reply_stream(self):
        if not getattr(self, "_stream_words", None):
            return
        total = len(self._stream_words)
        # Advance 2-3 words per 16ms frame (~120-150 words/sec: fast, responsive, buttery)
        step = max(2, total // 22)
        self._stream_idx = min(total, self._stream_idx + step)
        partial = " ".join(self._stream_words[:self._stream_idx])

        self.reply_text.config(state="normal")
        self.reply_text.delete("1.0", tk.END)
        self.reply_text.insert("1.0", partial)
        self.reply_text.config(state="disabled")

        if self._stream_idx >= total:
            self._stream_words = None
            self.reply_text.yview_moveto(0.0)

    def _set_reply_content(self, text: str):
        if text != self._last_rendered_reply:
            self._last_rendered_reply = text
            clean = text.strip()
            words = clean.split()
            # If short query or error/status, show immediately
            if len(words) <= 3 or clean.startswith("Processing") or clean.startswith("Voice received") or clean.startswith("Error:"):
                self._stream_words = None
                self.reply_text.config(state="normal")
                self.reply_text.delete("1.0", tk.END)
                self.reply_text.insert("1.0", clean)
                self.reply_text.config(state="disabled")
                self.reply_text.yview_moveto(0.0)
            else:
                # Start smooth stream typewriter reveal
                self._stream_words = words
                self._stream_idx = 0
                self.reply_text.config(state="normal")
                self.reply_text.delete("1.0", tk.END)
                self.reply_text.config(state="disabled")

    def _update_geometry(self):
        gw = self.WIN_W if getattr(self, "expanded", False) else 240
        gh = self.WIN_H if getattr(self, "expanded", False) else 56
        gx = int((getattr(self, "screen_w", 1920) - gw) / 2)
        gy = 0
        self.root.geometry(f"{gw}x{gh}+{gx}+{gy}")
        if hasattr(self, "canvas"):
            self.canvas.config(width=gw, height=gh)

    def _anim_loop(self):
        try:
            self._process_ui_queue()

            # Advance animation phase and sample time step dt
            now = time.perf_counter()
            dt = min(0.032, max(0.001, now - getattr(self, "_last_tick_time", now)))
            self._last_tick_time = now

            self._anim_phase += 0.06
            self._cur_cpu_pct += (self._target_cpu_pct - self._cur_cpu_pct) * 0.12
            self._cur_ram_pct += (self._target_ram_pct - self._cur_ram_pct) * 0.12

            # Determine mood for Wobnimo mascot
            has_approval = bool(getattr(self.asst, "pending_briefing", False) or getattr(self.asst, "pending_url", None))
            if self.mascot.is_celebrating:
                current_mood = "celebrating"
            elif has_approval:
                current_mood = "approval"
            elif self.is_listening and self.status_label == "Listening":
                current_mood = "listening"
            elif self.is_speaking:
                current_mood = "speaking"
            elif self.is_thinking:
                current_mood = "thinking"
            elif (now - getattr(self, "_last_user_activity", now)) > 300.0:
                current_mood = "sleeping"
            else:
                current_mood = "online"

            # Step Wobnimo spring physics & procedural animations
            self.mascot.update(
                dt=dt,
                mood=current_mood,
                is_speaking=self.is_speaking,
                is_listening=self.is_listening,
                audio_level=self._smooth_audio_level
            )

            # Smooth live audio level tracking for waveform visualizer
            try:
                import audio
                raw_level = getattr(audio, "LATEST_AUDIO_LEVEL", 0.0)
            except Exception:
                raw_level = 0.0
            self._smooth_audio_level += (raw_level - self._smooth_audio_level) * 0.35

            # Smooth response streaming reveal
            self._update_reply_stream()

            if getattr(self, "_animating", False):
                # Euler Spring Physics Simulation (signature organic Apple / Nixi bounce):
                # F = -k * (x - target) - c * v
                # a = F (with normalized mass m = 1.0)
                # v += a * dt
                # x += v * dt
                force_w = -self.spring_k * (self.cur_w - self.target_w) - self.spring_c * self.vel_w
                self.vel_w += force_w * dt
                self.cur_w += self.vel_w * dt

                force_h = -self.spring_k * (self.cur_h - self.target_h) - self.spring_c * self.vel_h
                self.vel_h += force_h * dt
                self.cur_h += self.vel_h * dt

                # Settle condition: low displacement and low velocity
                if (abs(self.cur_w - self.target_w) < 0.6 and abs(self.vel_w) < 1.5 and
                    abs(self.cur_h - self.target_h) < 0.6 and abs(self.vel_h) < 1.5):
                    self.cur_w = self.target_w
                    self.cur_h = self.target_h
                    self.vel_w = 0.0
                    self.vel_h = 0.0
                    self._animating = False

            self.telemetry_tick += 1
            if self.telemetry_tick % 180 == 0:
                self.telemetry = get_system_telemetry()
                try:
                    self._target_cpu_pct = float(self.telemetry["cpu"].rstrip("%"))
                    self._target_ram_pct = float(self.telemetry["ram"].rstrip("%"))
                except Exception:
                    pass

            self._render()
        except Exception:
            pass
        finally:
            self.root.after(16, self._anim_loop)

    def _hide_wave_items(self):
        for itm in (self.item_wave_bar1, self.item_wave_bar2, self.item_wave_bar3, getattr(self, "item_wave_bar4", None)):
            if itm is not None:
                self.canvas.itemconfig(itm, state="hidden")

    def _hide_media_compact_items(self):
        for itm in (
            getattr(self, "item_media_disc", None),
            getattr(self, "item_media_hole", None),
            getattr(self, "item_media_title", None),
            getattr(self, "item_media_artist", None),
            getattr(self, "item_media_bar1", None),
            getattr(self, "item_media_bar2", None),
            getattr(self, "item_media_bar3", None),
            getattr(self, "item_media_bar4", None),
        ):
            if itm is not None:
                self.canvas.itemconfig(itm, state="hidden")

    def _render(self):
        w = int(self.cur_w)
        h = int(self.cur_h)
        if w < 10 or h < 10:
            return

        has_approval = bool(getattr(self.asst, "pending_briefing", False) or getattr(self.asst, "pending_url", None) or getattr(self.asst, "pending_memory_cleanup", False))
        now = time.perf_counter()

        is_mic_hud = getattr(self, "hud_mic_active", False) and (now < getattr(self, "hud_mic_until", 0.0))
        is_vol_hud = getattr(self, "hud_volume_active", False) and (now < getattr(self, "hud_volume_until", 0.0))
        is_media_active = bool(getattr(self, "media_state", None) and self.media_state.is_playing and not (self.is_speaking or self.is_listening or self.is_thinking))

        if is_mic_hud and self.hud_mic_muted:
            mood = "mic_muted"
        elif is_media_active:
            mood = "media"
        elif self.mascot.is_celebrating:
            mood = "celebrating"
        elif has_approval:
            mood = "approval"
        elif self.is_listening and self.status_label == "Listening":
            mood = "listening"
        elif self.is_speaking:
            mood = "speaking"
        elif self.is_thinking:
            mood = "thinking"
        elif (now - getattr(self, "_last_user_activity", now)) > 300.0:
            mood = "sleeping"
        else:
            mood = "online"

        bg_photo = self._get_bg_photo(w, h, mood, self.expanded)
        self.canvas.itemconfig(self.item_bg, image=bg_photo)
        self.canvas.coords(self.item_bg, 0, 0)

        # ----------------------------------------------------------------------
        # COMPACT NOTCH / ISLAND MODE (w = 240, h = 56)
        # ----------------------------------------------------------------------
        if not self.expanded:
            self.input_frame.place_forget()
            if hasattr(self, "reply_frame"):
                self.reply_frame.place_forget()
            self._hide_expanded_items()
            for b in (getattr(self, "exp_wave_bar1", None), getattr(self, "exp_wave_bar2", None),
                      getattr(self, "exp_wave_bar3", None), getattr(self, "exp_wave_bar4", None),
                      getattr(self, "exp_wave_bar5", None)):
                if b is not None:
                    self.canvas.itemconfig(b, state="hidden")

            cy = 28.0

            # CASE A: Mic Sentinel HUD
            if is_mic_hud:
                self.canvas.itemconfig(self.item_compact_robo, state="hidden")
                self.canvas.itemconfig(self.item_compact_title, state="hidden")
                self.canvas.itemconfig(self.item_compact_status, state="hidden")
                self._hide_media_compact_items()
                self._hide_wave_items()

                self.canvas.coords(self.item_hud_icon, 24, cy)
                self.canvas.itemconfig(self.item_hud_icon, text="🎙️", state="normal")

                hud_txt = "MIC MUTED" if self.hud_mic_muted else "MIC ACTIVE"
                hud_color = "#ef4444" if self.hud_mic_muted else "#10b981"
                self.canvas.coords(self.item_hud_text, 44, cy - 7)
                self.canvas.itemconfig(self.item_hud_text, text=hud_txt, fill=hud_color, state="normal")

                self.canvas.coords(self.item_hud_sub, 44, cy + 7)
                self.canvas.itemconfig(self.item_hud_sub, text="Ctrl+Alt+M to toggle", fill="#a3a3a3", state="normal")

                self.canvas.itemconfig(self.item_hud_track, state="hidden")
                self.canvas.itemconfig(self.item_hud_fill, state="hidden")
                self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
                return

            # CASE B: Volume HUD
            elif is_vol_hud:
                self.canvas.itemconfig(self.item_compact_robo, state="hidden")
                self.canvas.itemconfig(self.item_compact_title, state="hidden")
                self.canvas.itemconfig(self.item_compact_status, state="hidden")
                self._hide_media_compact_items()
                self._hide_wave_items()

                vol_icon = "🔇" if self.hud_volume_muted else "🔊"
                self.canvas.coords(self.item_hud_icon, 24, cy)
                self.canvas.itemconfig(self.item_hud_icon, text=vol_icon, state="normal")

                self.canvas.coords(self.item_hud_text, 44, cy)
                self.canvas.itemconfig(self.item_hud_text, text=f"{self.hud_volume_val}%", fill="#f5f5f5", state="normal")

                bx = 82.0
                bw = 130.0
                pts_tr = _rounded_rect_points(bx, cy - 3.0, bx + bw, cy + 3.0, r=3.0)
                self.canvas.coords(self.item_hud_track, pts_tr)
                self.canvas.itemconfig(self.item_hud_track, fill="#262626", state="normal")

                fill_w = max(4.0, (self.hud_volume_val / 100.0) * bw)
                pts_fl = _rounded_rect_points(bx, cy - 3.0, bx + fill_w, cy + 3.0, r=3.0)
                self.canvas.coords(self.item_hud_fill, pts_fl)
                self.canvas.itemconfig(self.item_hud_fill, fill="#38bdf8", state="normal")

                self.canvas.itemconfig(self.item_hud_sub, state="hidden")
                self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
                return

            # Hide HUD items if not active
            self.canvas.itemconfig(self.item_hud_icon, state="hidden")
            self.canvas.itemconfig(self.item_hud_text, state="hidden")
            self.canvas.itemconfig(self.item_hud_sub, state="hidden")
            self.canvas.itemconfig(self.item_hud_track, state="hidden")
            self.canvas.itemconfig(self.item_hud_fill, state="hidden")

            # CASE C: Now Playing Media Island
            if is_media_active:
                self.canvas.itemconfig(self.item_compact_robo, state="hidden")
                self.canvas.itemconfig(self.item_compact_title, state="hidden")
                self.canvas.itemconfig(self.item_compact_status, state="hidden")
                self._hide_wave_items()

                cx_disc = 24.0
                self.canvas.coords(self.item_media_disc, cx_disc - 10, cy - 10, cx_disc + 10, cy + 10)
                self.canvas.coords(self.item_media_hole, cx_disc - 3, cy - 3, cx_disc + 3, cy + 3)
                self.canvas.itemconfig(self.item_media_disc, state="normal")
                self.canvas.itemconfig(self.item_media_hole, state="normal")

                avail_mw = 135
                disp_title = self._truncate_text_to_width(self.media_state.title or "Playing", self.font_compact_title, avail_mw)
                art_lbl = f"{self.media_state.artist} • {self.media_state.source_app}" if self.media_state.artist else self.media_state.source_app
                disp_artist = self._truncate_text_to_width(art_lbl, self.font_compact_status, avail_mw)

                self.canvas.coords(self.item_media_title, 42, cy - 7)
                self.canvas.itemconfig(self.item_media_title, text=disp_title, state="normal")
                self.canvas.coords(self.item_media_artist, 42, cy + 7)
                self.canvas.itemconfig(self.item_media_artist, text=disp_artist, state="normal")

                eq_x = 206.0
                eq_bars = (self.item_media_bar1, self.item_media_bar2, self.item_media_bar3, self.item_media_bar4)
                eq_offs = (-8.0, -2.5, 3.0, 8.5)
                eq_freqs = (5.2, 7.1, 4.4, 6.6)
                eq_p_offs = (0.0, 1.4, 2.7, 4.0)

                for bar_item, off, freq, p_off in zip(eq_bars, eq_offs, eq_freqs, eq_p_offs):
                    bh = max(3.5, min(16.0, 4.0 + 11.0 * abs(math.sin(self._anim_phase * freq + p_off))))
                    pts = _rounded_rect_points(eq_x + off - 1.2, cy - bh / 2, eq_x + off + 1.2, cy + bh / 2, r=1.2)
                    self.canvas.coords(bar_item, pts)
                    self.canvas.itemconfig(bar_item, fill="#1db954", state="normal")

                self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
                return

            # CASE D: Default Assistant Compact Notch (React iOS Dynamic Island Pill)
            self._hide_media_compact_items()
            robo_img = self.mascot.get_photo_image(size=26, mood=mood, phase=self._anim_phase)
            self.canvas.coords(self.item_compact_robo, 30.0, cy)
            self.canvas.itemconfig(self.item_compact_robo, image=robo_img, state="normal")

            self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
            is_mic_muted = bool(hasattr(self, "sys_sentinel") and self.sys_sentinel and self.sys_sentinel.get_mic_mute())

            is_active_listening = (self.is_listening and self.status_label == "Listening")
            is_active_wave = bool(is_active_listening or self.is_speaking)

            # Title
            self.canvas.coords(self.item_compact_title, 48.0, cy)
            self.canvas.itemconfig(self.item_compact_title, text="J.A.R.V.I.S.", state="normal")

            # Siri-style 3-Bar Animated Waveform
            wave_cx = 124.0
            if is_active_wave:
                if self.is_speaking:
                    speech_mod = 0.55 + 0.35 * math.sin(self._anim_phase * 3.2) + 0.15 * math.cos(self._anim_phase * 6.5)
                    level = max(0.25, min(1.0, speech_mod))
                else:
                    level = min(1.0, max(0.15, self._smooth_audio_level * 180.0))
                b1_h = max(3.5, min(16.0, 5.0 + 11.0 * level * abs(math.sin(self._anim_phase * 4.5))))
                b2_h = max(4.0, min(20.0, 6.0 + 14.0 * level * abs(math.sin(self._anim_phase * 6.2 + 1.2))))
                b3_h = max(3.0, min(14.0, 4.0 + 10.0 * level * abs(math.sin(self._anim_phase * 3.8 + 2.4))))
            else:
                b1_h = max(3.0, 4.0 + 3.0 * abs(math.sin(self._anim_phase * 2.8)))
                b2_h = max(4.0, 7.0 + 4.0 * abs(math.sin(self._anim_phase * 3.5 + 1.0)))
                b3_h = max(2.5, 3.5 + 2.5 * abs(math.sin(self._anim_phase * 2.2 + 2.0)))

            pts_b1 = _rounded_rect_points(wave_cx - 5.0, cy - b1_h / 2, wave_cx - 3.0, cy + b1_h / 2, r=1.0)
            pts_b2 = _rounded_rect_points(wave_cx - 1.0, cy - b2_h / 2, wave_cx + 1.0, cy + b2_h / 2, r=1.0)
            pts_b3 = _rounded_rect_points(wave_cx + 3.0, cy - b3_h / 2, wave_cx + 5.0, cy + b3_h / 2, r=1.0)
            self.canvas.coords(self.item_wave_bar1, pts_b1)
            self.canvas.coords(self.item_wave_bar2, pts_b2)
            self.canvas.coords(self.item_wave_bar3, pts_b3)
            self.canvas.itemconfig(self.item_wave_bar1, fill="#22d3ee", state="normal")
            self.canvas.itemconfig(self.item_wave_bar2, fill="#818cf8", state="normal")
            self.canvas.itemconfig(self.item_wave_bar3, fill="#fb7185", state="normal")
            if getattr(self, "item_wave_bar4", None):
                self.canvas.itemconfig(self.item_wave_bar4, state="hidden")

            # Vertical divider
            div_x = 140.0
            self.canvas.coords(self.item_compact_div, div_x, cy - 8.0, div_x, cy + 8.0)
            self.canvas.itemconfig(self.item_compact_div, fill="#334155", state="normal")

            # Status text & chevron
            badge_txt = self.current_tool_badge or ("🎙️ Muted" if is_mic_muted else self.status_label)
            status_clr = "#f43f5e" if is_mic_muted else ("#34d399" if self.status_label == "Ready" else self.status_color)
            self.canvas.coords(self.item_compact_status, div_x + 8.0, cy)
            self.canvas.itemconfig(self.item_compact_status, text=badge_txt, fill=status_clr, state="normal")

            self.canvas.coords(self.item_compact_chevron, 214.0, cy)
            self.canvas.itemconfig(self.item_compact_chevron, text="⤢", fill="#64748b", state="normal")
            return

        # ----------------------------------------------------------------------
        # EXPANDED MODE (w = 780, h = 360)
        # ----------------------------------------------------------------------
        self._hide_media_compact_items()

        # 1. Top Dynamic Island Pill (Centered at 390, y = 6 -> 50, cy = 28.0)
        pill_x = 280.0
        cy = 28.0
        robo_img = self.mascot.get_photo_image(size=26, mood=mood, phase=self._anim_phase)
        self.canvas.coords(self.item_compact_robo, pill_x + 20.0, cy)
        self.canvas.itemconfig(self.item_compact_robo, image=robo_img, state="normal")

        self.canvas.coords(self.item_compact_title, pill_x + 38.0, cy)
        self.canvas.itemconfig(self.item_compact_title, text="J.A.R.V.I.S.", state="normal")

        # Siri-style Waveform inside Top Pill
        wave_cx = pill_x + 114.0
        b1_h = max(3.0, 4.0 + 3.0 * abs(math.sin(self._anim_phase * 2.8)))
        b2_h = max(4.0, 7.0 + 4.0 * abs(math.sin(self._anim_phase * 3.5 + 1.0)))
        b3_h = max(2.5, 3.5 + 2.5 * abs(math.sin(self._anim_phase * 2.2 + 2.0)))
        pts_b1 = _rounded_rect_points(wave_cx - 5.0, cy - b1_h / 2, wave_cx - 3.0, cy + b1_h / 2, r=1.0)
        pts_b2 = _rounded_rect_points(wave_cx - 1.0, cy - b2_h / 2, wave_cx + 1.0, cy + b2_h / 2, r=1.0)
        pts_b3 = _rounded_rect_points(wave_cx + 3.0, cy - b3_h / 2, wave_cx + 5.0, cy + b3_h / 2, r=1.0)
        self.canvas.coords(self.item_wave_bar1, pts_b1)
        self.canvas.coords(self.item_wave_bar2, pts_b2)
        self.canvas.coords(self.item_wave_bar3, pts_b3)
        self.canvas.itemconfig(self.item_wave_bar1, fill="#22d3ee", state="normal")
        self.canvas.itemconfig(self.item_wave_bar2, fill="#818cf8", state="normal")
        self.canvas.itemconfig(self.item_wave_bar3, fill="#fb7185", state="normal")

        div_x = pill_x + 130.0
        self.canvas.coords(self.item_compact_div, div_x, cy - 8.0, div_x, cy + 8.0)
        self.canvas.itemconfig(self.item_compact_div, fill="#334155", state="normal")

        is_mic_muted = bool(hasattr(self, "sys_sentinel") and self.sys_sentinel and self.sys_sentinel.get_mic_mute())
        badge_txt = self.current_tool_badge or ("🎙️ Muted" if is_mic_muted else self.status_label)
        status_clr = "#f43f5e" if is_mic_muted else ("#34d399" if self.status_label == "Ready" else self.status_color)
        self.canvas.coords(self.item_compact_status, div_x + 8.0, cy)
        self.canvas.itemconfig(self.item_compact_status, text=badge_txt, fill=status_clr, state="normal")

        self.canvas.coords(self.item_compact_chevron, pill_x + 204.0, cy)
        self.canvas.itemconfig(self.item_compact_chevron, text="⤡", fill="#64748b", state="normal")

        # 2. Expanded 3-Card Deck Architecture (y: 60 -> 340)
        deck_y = 60.0
        deck_h = 280.0
        left_w = 460.0
        card_lx1 = 10.0
        card_lx2 = card_lx1 + left_w  # 470.0
        card_ly1 = deck_y             # 60.0
        card_ly2 = card_ly1 + deck_h  # 340.0

        gap = 10.0
        right_x = card_lx2 + gap      # 480.0
        right_w = 290.0
        rx2 = right_x + right_w       # 770.0
        rc_h = (deck_h - gap) // 2    # 135.0

        # --- LEFT CARD: ASSISTANT INTELLIGENCE DECK ---
        # Header (Top of Left Card)
        robo_large = self.mascot.get_photo_image(size=30, mood=mood, phase=self._anim_phase)
        self.canvas.coords(self.item_agent_robo, card_lx1 + 26.0, card_ly1 + 24.0)
        self.canvas.itemconfig(self.item_agent_robo, image=robo_large, state="normal")

        self.canvas.coords(self.item_agent_title, card_lx1 + 48.0, card_ly1 + 17.0)
        self.canvas.itemconfig(self.item_agent_title, text="Assistant Intelligence", state="normal")
        self.canvas.coords(self.item_agent_sub, card_lx1 + 48.0, card_ly1 + 31.0)
        self.canvas.itemconfig(self.item_agent_sub, text="NEURAL LINK // ACTIVE", state="normal")

        # Optimal / Status Pill Badge
        badge_w = 58.0
        badge_h = 20.0
        bx2 = card_lx2 - 16.0
        bx1 = bx2 - badge_w
        by1 = card_ly1 + 14.0
        by2 = by1 + badge_h
        pts_badge = _rounded_rect_points(bx1, by1, bx2, by2, r=10.0)
        self.canvas.coords(self.item_agent_badge_bg, pts_badge)
        self.canvas.coords(self.item_agent_badge, (bx1 + bx2) / 2.0, (by1 + by2) / 2.0)

        if self.is_listening:
            badge_txt = "Listening"
            b_fill, b_outline, t_fill = "#881337", "#f43f5e", "#fb7185"
        elif self.is_thinking:
            badge_txt = "Working"
            b_fill, b_outline, t_fill = "#78350f", "#f59e0b", "#fbbf24"
        elif self.is_speaking:
            badge_txt = "Speaking"
            b_fill, b_outline, t_fill = "#064e3b", "#10b981", "#34d399"
        else:
            badge_txt = "Optimal"
            b_fill, b_outline, t_fill = "#064e3b", "#059669", "#34d399"

        self.canvas.itemconfig(self.item_agent_badge_bg, fill=b_fill, outline=b_outline, state="normal")
        self.canvas.itemconfig(self.item_agent_badge, text=badge_txt, fill=t_fill, state="normal")

        # Bottom Prompt Pill Bar (iOS Frosted Pill Bar)
        input_y = card_ly2 - 46.0   # 294.0
        input_h = 32.0
        input_x1 = card_lx1 + 16.0  # 26.0
        input_x2 = card_lx2 - 16.0  # 454.0
        input_w = input_x2 - input_x1
        pts_in = _rounded_rect_points(input_x1, input_y, input_x2, input_y + input_h, r=16.0)
        self.canvas.coords(self.item_input_box, pts_in)
        self.canvas.itemconfig(self.item_input_box, fill="#141926", outline="#334155", state="normal")

        entry_w = max(40, int(input_w - 76.0))
        self.input_frame.place(x=int(input_x1 + 14.0), y=int(input_y + 4.0), width=entry_w, height=int(input_h - 8.0))

        # Mic & Send Buttons inside Prompt Pill Bar
        mic_cx = input_x2 - 46.0
        mic_cy = input_y + input_h / 2.0
        r_btn = 11.0
        self._btn_mic_cx = mic_cx
        self._btn_mic_cy = mic_cy
        self.canvas.coords(self.item_btn_mic_bg, mic_cx - r_btn, mic_cy - r_btn, mic_cx + r_btn, mic_cy + r_btn)
        self.canvas.coords(self.item_btn_mic, mic_cx, mic_cy)
        if self.is_listening:
            self.canvas.itemconfig(self.item_btn_mic_bg, fill="#881337", outline="#f43f5e", state="normal")
            self.canvas.itemconfig(self.item_btn_mic, fill="#fb7185", state="normal")
        else:
            self.canvas.itemconfig(self.item_btn_mic_bg, fill="#1e2538", outline="#334155", state="normal")
            self.canvas.itemconfig(self.item_btn_mic, fill="#94a3b8", state="normal")

        send_cx = input_x2 - 18.0
        send_cy = input_y + input_h / 2.0
        self._btn_send_cx = send_cx
        self._btn_send_cy = send_cy
        self.canvas.coords(self.item_btn_send_bg, send_cx - r_btn, send_cy - r_btn, send_cx + r_btn, send_cy + r_btn)
        self.canvas.coords(self.item_btn_send, send_cx, send_cy)
        self.canvas.itemconfig(self.item_btn_send_bg, fill="#ffffff", outline="", state="normal")
        self.canvas.itemconfig(self.item_btn_send, text="➤", fill="#000000", state="normal")

        # Middle Response Bubble & Action Chips
        bubble_x1 = card_lx1 + 16.0
        bubble_y1 = card_ly1 + 48.0   # 108.0
        bubble_x2 = card_lx2 - 16.0   # 454.0
        bubble_y2 = input_y - 8.0     # 286.0

        if has_approval and left_w >= 140:
            if getattr(self.asst, "pending_url", None):
                raw_lbl = getattr(self.asst, "pending_label", "") or "Google"
                clean_lbl = raw_lbl if len(raw_lbl) <= 15 else f"{raw_lbl[:13]}.."
                app_lbl = f"🔗 View on {clean_lbl}"
                den_lbl = "✕ Dismiss"
            elif getattr(self.asst, "pending_memory_cleanup", False):
                app_lbl = "✓ Optimize"
                den_lbl = "✕ Dismiss"
            elif getattr(self.asst, "pending_briefing", False):
                app_lbl = "✓ Start Briefing"
                den_lbl = "✕ Not Now"
            else:
                app_lbl, den_lbl = "✓ Yes", "✕ No"

            app_w = max(68.0, self.font_chip_bold.measure(app_lbl) + 30.0)
            den_w = max(68.0, self.font_chip_norm.measure(den_lbl) + 30.0)
            chip_h = 24.0
            gap_chip = 12.0

            total_chips_w = app_w + gap_chip + den_w
            cx_card = (bubble_x1 + bubble_x2) / 2.0
            x1_app = max(bubble_x1 + 6.0, cx_card - total_chips_w / 2.0)
            x2_app = x1_app + app_w
            x1_den = x2_app + gap_chip
            x2_den = x1_den + den_w

            chip_y = bubble_y2 - chip_h - 4.0
            avail_h = max(20.0, chip_y - bubble_y1 - 8.0)

            self.chip_approve_bbox = (int(x1_app), int(chip_y), int(x2_app), int(chip_y + chip_h))
            self.chip_deny_bbox = (int(x1_den), int(chip_y), int(x2_den), int(chip_y + chip_h))

            lift_app = 2.0 if getattr(self, "_hover_chip", None) == "approve" else 0.0
            pts_app = _rounded_rect_points(x1_app, chip_y - lift_app, x2_app, chip_y + chip_h - lift_app, r=8.0)
            self.canvas.coords(self.item_chip_approve_bg, pts_app)
            self.canvas.coords(self.item_chip_approve_text, (x1_app + x2_app) / 2.0, chip_y + chip_h / 2.0 - lift_app)
            app_fill = "#059669" if lift_app > 0 else "#262626"
            app_outline = "#34d399" if lift_app > 0 else "#525252"
            self.canvas.itemconfig(self.item_chip_approve_bg, fill=app_fill, outline=app_outline, state="normal")
            self.canvas.itemconfig(self.item_chip_approve_text, text=app_lbl, state="normal")

            lift_den = 2.0 if getattr(self, "_hover_chip", None) == "deny" else 0.0
            pts_den = _rounded_rect_points(x1_den, chip_y - lift_den, x2_den, chip_y + chip_h - lift_den, r=8.0)
            self.canvas.coords(self.item_chip_deny_bg, pts_den)
            self.canvas.coords(self.item_chip_deny_text, (x1_den + x2_den) / 2.0, chip_y + chip_h / 2.0 - lift_den)
            den_fill = "#991b1b" if lift_den > 0 else "#171717"
            den_outline = "#f87171" if lift_den > 0 else "#333333"
            self.canvas.itemconfig(self.item_chip_deny_bg, fill=den_fill, outline=den_outline, state="normal")
            self.canvas.itemconfig(self.item_chip_deny_text, text=den_lbl, state="normal")
        else:
            self.canvas.itemconfig(self.item_chip_approve_bg, state="hidden")
            self.canvas.itemconfig(self.item_chip_approve_text, state="hidden")
            self.canvas.itemconfig(self.item_chip_deny_bg, state="hidden")
            self.canvas.itemconfig(self.item_chip_deny_text, state="hidden")
            self.chip_approve_bbox = None
            self.chip_deny_bbox = None
            avail_h = max(20.0, bubble_y2 - bubble_y1 - 10.0)

        reply_val = self.last_reply or "Operating at peak efficiency. All telemetry parameters are nominal. Would you like me to pull up your daily digest or verify your scheduled tasks?"
        clean = str(reply_val).replace("\x00", "").replace("\r", " ").strip()
        self._set_reply_content(clean)
        self.reply_frame.place(x=int(bubble_x1 + 6.0), y=int(bubble_y1 + 6.0), width=int(bubble_x2 - bubble_x1 - 12.0), height=int(avail_h))
        self.canvas.itemconfig(self.item_reply_text, state="hidden")

        # --- RIGHT CARD 1: IOS LOCKSCREEN CLOCK CARD ---
        rx1 = right_x                # 480.0
        ry1 = card_ly1               # 60.0
        ry2 = ry1 + rc_h             # 195.0

        # Header: CLOCK + Window Control Buttons (— and ✕)
        self.canvas.coords(self.item_clock_hdr, rx1 + 16.0, ry1 + 14.0)
        self.canvas.itemconfig(self.item_clock_hdr, state="normal")

        self.canvas.coords(self.item_clock_icon, rx2 - 50.0, ry1 + 14.0)
        self.canvas.itemconfig(self.item_clock_icon, text="🔊", state="normal")

        self.canvas.coords(self.item_btn_min, rx2 - 32.0, ry1 + 14.0)
        self.canvas.itemconfig(self.item_btn_min, text="—", state="normal")

        self.canvas.coords(self.item_btn_close, rx2 - 16.0, ry1 + 14.0)
        self.canvas.itemconfig(self.item_btn_close, text="✕", state="normal")

        # Large Digital Time & Date
        now_dt = datetime.datetime.now()
        hh_str = now_dt.strftime("%H")
        mm_str = now_dt.strftime("%M")
        date_str = now_dt.strftime("%A, %d %b")

        colon_val = int(140 + 115 * math.sin(self._anim_phase * 2.8))
        colon_fill = f"#{colon_val:02x}{colon_val:02x}{colon_val:02x}"

        hh_w = self.font_clock.measure(hh_str)
        colon_w = self.font_clock.measure(":")

        self.canvas.coords(self.item_clock_time, rx1 + 16.0, ry1 + 32.0)
        self.canvas.itemconfig(self.item_clock_time, text=hh_str, fill="#ffffff", state="normal")

        self.canvas.coords(self.item_clock_colon, rx1 + 16.0 + hh_w, ry1 + 32.0)
        self.canvas.itemconfig(self.item_clock_colon, text=":", fill=colon_fill, state="normal")

        self.canvas.coords(self.item_clock_mm, rx1 + 16.0 + hh_w + colon_w, ry1 + 32.0)
        self.canvas.itemconfig(self.item_clock_mm, text=mm_str, fill="#ffffff", state="normal")

        self.canvas.coords(self.item_clock_date, rx1 + 16.0, ry1 + 68.0)
        self.canvas.itemconfig(self.item_clock_date, text=date_str, fill="#94a3b8", state="normal")

        # Divider & Footer
        self.canvas.coords(self.item_clock_div, rx1 + 16.0, ry1 + 94.0, rx2 - 16.0, ry1 + 94.0)
        self.canvas.itemconfig(self.item_clock_div, fill="#1e293b", state="normal")

        has_media = bool(getattr(self, "media_state", None) and self.media_state.is_active)
        if has_media:
            footer_txt = f"▶ {self.media_state.title or 'Playing'}"
            footer_clr = "#10b981"
        else:
            footer_txt = "● System Time Synced"
            footer_clr = "#22d3ee"

        self.canvas.coords(self.item_clock_footer, rx1 + 16.0, ry1 + 104.0)
        self.canvas.itemconfig(self.item_clock_footer, text=footer_txt, fill=footer_clr, state="normal")

        # --- RIGHT CARD 2: BATTERY & TELEMETRY CARD ---
        rx2_1 = right_x              # 480.0
        ry2_1 = ry2 + gap            # 205.0
        rx2_2 = rx2                  # 770.0
        ry2_2 = ry2_1 + rc_h         # 340.0

        # Battery Badge & Tag
        bat_str = self.telemetry.get("bat", "44% Charging")
        is_charging = "Charging" in bat_str or "Plugged" in bat_str

        bx1 = rx2_1 + 16.0           # 496.0
        by1 = ry2_1 + 14.0           # 219.0
        bx2 = bx1 + 24.0             # 520.0
        by2 = by1 + 24.0             # 243.0
        pts_bg = _rounded_rect_points(bx1, by1, bx2, by2, r=6.0)
        self.canvas.coords(self.item_bat_badge, pts_bg)
        self.canvas.itemconfig(self.item_bat_badge, fill="#064e3b", outline="#059669", state="normal")

        bw, bh = 9.0, 14.0
        bx = bx1 + 7.5
        by = by1 + 5.0
        pts_bolt = [
            bx + 0.632 * bw, by + 0.000 * bh,
            bx + 0.000 * bw, by + 0.514 * bh,
            bx + 0.368 * bw, by + 0.595 * bh,
            bx + 0.368 * bw, by + 1.000 * bh,
            bx + 1.000 * bw, by + 0.459 * bh,
            bx + 0.632 * bw, by + 0.405 * bh,
        ]
        self.canvas.coords(self.item_bolt, pts_bolt)
        self.canvas.itemconfig(self.item_bolt, fill="#34d399", state="normal")

        self.canvas.coords(self.item_sys_bat, bx2 + 10.0, by1 + 4.0)
        self.canvas.itemconfig(self.item_sys_bat, text=bat_str, fill="#f8fafc", state="normal")

        tag_txt = "FAST" if is_charging else "AC"
        self.canvas.coords(self.item_bat_tag, rx2_2 - 16.0, by1 + 12.0)
        self.canvas.itemconfig(self.item_bat_tag, text=tag_txt, fill="#34d399", state="normal")

        # Hardware Metrics Micro-Gauges (CPU & RAM)
        bar_x = rx2_1 + 78.0
        bar_w = max(30.0, rx2_2 - bar_x - 16.0)

        # CPU Row
        cpu_val = max(0.0, min(100.0, self._cur_cpu_pct))
        cpu_fill_w = max(3.0, (cpu_val / 100.0) * bar_w)
        cpu_color = "#f43f5e" if cpu_val > 85.0 else ("#f59e0b" if cpu_val > 70.0 else "#38bdf8")
        y_cpu = ry2_1 + 54.0

        self.canvas.coords(self.item_cpu_lbl, rx2_1 + 16.0, y_cpu - 6.0)
        self.canvas.itemconfig(self.item_cpu_lbl, text=f"CPU {cpu_val:.0f}%", fill="#94a3b8", state="normal")

        pts_cpu_tr = _rounded_rect_points(bar_x, y_cpu - 2.0, bar_x + bar_w, y_cpu + 2.0, r=2.0)
        self.canvas.coords(self.item_cpu_track, pts_cpu_tr)
        self.canvas.itemconfig(self.item_cpu_track, fill="#1e2433", state="normal")

        pts_cpu_fl = _rounded_rect_points(bar_x, y_cpu - 2.0, bar_x + cpu_fill_w, y_cpu + 2.0, r=2.0)
        self.canvas.coords(self.item_cpu_fill, pts_cpu_fl)
        self.canvas.itemconfig(self.item_cpu_fill, fill=cpu_color, state="normal")

        # RAM Row
        ram_val = max(0.0, min(100.0, self._cur_ram_pct))
        ram_fill_w = max(3.0, (ram_val / 100.0) * bar_w)
        ram_color = "#f43f5e" if ram_val > 85.0 else ("#f59e0b" if ram_val > 75.0 else "#f59e0b")
        y_ram = ry2_1 + 84.0

        self.canvas.coords(self.item_ram_lbl, rx2_1 + 16.0, y_ram - 6.0)
        self.canvas.itemconfig(self.item_ram_lbl, text=f"RAM {ram_val:.0f}%", fill="#94a3b8", state="normal")

        pts_ram_tr = _rounded_rect_points(bar_x, y_ram - 2.0, bar_x + bar_w, y_ram + 2.0, r=2.0)
        self.canvas.coords(self.item_ram_track, pts_ram_tr)
        self.canvas.itemconfig(self.item_ram_track, fill="#1e2433", state="normal")

        pts_ram_fl = _rounded_rect_points(bar_x, y_ram - 2.0, bar_x + ram_fill_w, y_ram + 2.0, r=2.0)
        self.canvas.coords(self.item_ram_fill, pts_ram_fl)
        self.canvas.itemconfig(self.item_ram_fill, fill=ram_color, state="normal")

    def _hide_expanded_items(self):
        if hasattr(self, "reply_frame"):
            self.reply_frame.place_forget()
        for item in (
            getattr(self, "item_header_logo", None),
            getattr(self, "item_btn_min", None),
            getattr(self, "item_btn_close", None),
            getattr(self, "item_agent_robo", None),
            getattr(self, "item_agent_title", None),
            getattr(self, "item_agent_sub", None),
            getattr(self, "item_agent_status", None),
            getattr(self, "item_agent_badge_bg", None),
            getattr(self, "item_agent_badge", None),
            getattr(self, "item_input_box", None),
            getattr(self, "item_btn_send_bg", None),
            getattr(self, "item_btn_send", None),
            getattr(self, "item_btn_mic_bg", None),
            getattr(self, "item_btn_mic", None),
            getattr(self, "item_reply_text", None),
            getattr(self, "item_chip_approve_bg", None),
            getattr(self, "item_chip_approve_text", None),
            getattr(self, "item_chip_deny_bg", None),
            getattr(self, "item_chip_deny_text", None),
            getattr(self, "item_clock_hdr", None),
            getattr(self, "item_clock_icon", None),
            getattr(self, "item_clock_time", None),
            getattr(self, "item_clock_colon", None),
            getattr(self, "item_clock_mm", None),
            getattr(self, "item_clock_date", None),
            getattr(self, "item_clock_div", None),
            getattr(self, "item_clock_footer", None),
            getattr(self, "item_bat_badge", None),
            getattr(self, "item_bolt_glow", None),
            getattr(self, "item_bolt", None),
            getattr(self, "item_sys_bat", None),
            getattr(self, "item_bat_tag", None),
            getattr(self, "item_cpu_lbl", None),
            getattr(self, "item_cpu_track", None),
            getattr(self, "item_cpu_fill", None),
            getattr(self, "item_ram_lbl", None),
            getattr(self, "item_ram_track", None),
            getattr(self, "item_ram_fill", None),
            getattr(self, "item_btn_style_toggle", None),
            getattr(self, "item_mc_badge", None),
            getattr(self, "item_mc_title", None),
            getattr(self, "item_mc_artist", None),
            getattr(self, "item_mc_prev", None),
            getattr(self, "item_mc_play", None),
            getattr(self, "item_mc_next", None),
            getattr(self, "item_mic_indicator", None),
        ):
            if item is not None:
                self.canvas.itemconfig(item, state="hidden")
        self.chip_approve_bbox = None
        self.chip_deny_bbox = None

    def on_send(self):
        self._cancel_collapse_timer()
        self.hover_expanded = False
        self.is_listening = False
        text = self.entry_var.get().strip()
        if not text or self._placeholder_active:
            return
        self.last_query = text
        self.entry_var.set("")
        self.status_label = "Thinking"
        self.status_color = "#f59e0b"
        self.is_thinking = True
        self.last_reply = f"Processing '{text}'..."
        self._recompute_target_size()
        threading.Thread(target=self._process_query, args=(text,), daemon=True).start()

    def _process_query(self, query: str):
        try:
            self.asst.handle(query)
        except Exception as e:
            self._post_ui(lambda: self._on_query_error(str(e)))
        finally:
            self._post_ui(self.keep_on_top)
            self._post_ui(lambda: self.root.after(1500, self._check_idle_after_query))

    def _check_idle_after_query(self):
        if self.is_thinking and not self.is_speaking:
            self._reset_status()

    def _on_query_error(self, err: str):
        self.status_label = "Ready"
        self.status_color = "#a3a3a3"
        self.is_thinking = False
        self.last_reply = f"Error: {err}"
        self._recompute_target_size()

    def on_mic_click(self):
        self._cancel_collapse_timer()
        self.hover_expanded = False
        if getattr(self, "is_speaking", False):
            if hasattr(self.asst, "speaker") and self.asst.speaker:
                self.asst.speaker.stop()
            self.is_speaking = False

        if self.is_listening:
            self.is_listening = False
            self.status_label = "Ready"
            self.status_color = "#a3a3a3"
        else:
            self.is_listening = True
            self.status_label = "Listening"
            self.status_color = "#f43f5e"
            threading.Thread(target=self._listen_worker, daemon=True).start()
        self._recompute_target_size()

    def _listen_worker(self):
        listener = None
        try:
            from audio import Listener, Transcriber, NOISE_PHRASES
            mic_id = os.environ.get("MIC_DEVICE", "").strip()
            dev = int(mic_id) if mic_id.isdigit() else (mic_id or None)
            listener = Listener(device=dev)
            listener.start()
            listener.calibrate(seconds=0.4)

            transcribe = Transcriber(
                model=os.environ.get("WHISPER_MODEL", "base.en"),
                device=os.environ.get("WHISPER_DEVICE", "cpu"),
                compute_type=os.environ.get("WHISPER_COMPUTE", "int8"),
            )
            phrase = listener.record_phrase()
            self.is_listening = False
            if phrase is not None and len(phrase) > 0:
                self._post_ui(self._set_status_thinking)
                text = transcribe(phrase).strip()
                if text and text.lower() not in NOISE_PHRASES:
                    self._post_ui(lambda: self._handle_voice_text(text))
                else:
                    self._post_ui(lambda: self._update_speech("I didn't catch that, sir."))
            else:
                self._post_ui(self._reset_status)
        except Exception as e:
            self.is_listening = False
            self._post_ui(lambda: self._update_speech("Microphone is currently unavailable."))
        finally:
            self.is_listening = False
            if listener:
                try:
                    listener.close()
                except Exception:
                    pass

    def _set_status_thinking(self):
        self.is_listening = False
        self.is_thinking = True
        self.status_label = "Thinking"
        self.status_color = "#f59e0b"
        self._recompute_target_size()

    def _update_speech(self, text: str):
        self.is_listening = False
        self.last_reply = text
        self._reset_status()
        if hasattr(self.asst, "speaker") and self.asst.speaker:
            import threading
            threading.Thread(target=self.asst.speak, args=(text,), daemon=True).start()

    def _handle_voice_text(self, text: str):
        self.is_listening = False
        self.last_query = text
        self.status_label = "Working"
        self.status_color = "#f59e0b"
        self.is_thinking = True
        self.last_reply = f"Voice received: '{text}'"
        self._recompute_target_size()
        threading.Thread(target=self._process_query, args=(text,), daemon=True).start()

    def _on_canvas_click(self, event):
        self._cancel_collapse_timer()
        if hasattr(self, "_reset_timer_id") and self._reset_timer_id is not None:
            try:
                self.root.after_cancel(self._reset_timer_id)
            except Exception:
                pass
            self._reset_timer_id = None
        x, y = event.x, event.y

        # Any user click locks the widget open
        self.hover_expanded = False

        if not self.expanded:
            self.toggle_expand(True)
            return

        # Check clicking Top Island Pill to collapse (Matches React Dynamic Island Pill click)
        if 280 <= x <= 500 and 6 <= y <= 50:
            self.toggle_expand(False)
            return

        # Check Minimize Button (—)
        if hasattr(self, "item_btn_min"):
            min_coords = self.canvas.coords(self.item_btn_min)
            if min_coords and (abs(x - min_coords[0]) <= 14) and (abs(y - min_coords[1]) <= 14):
                self.toggle_expand(False)
                return

        # Check Close Button (✕)
        if hasattr(self, "item_btn_close"):
            close_coords = self.canvas.coords(self.item_btn_close)
            if close_coords and (abs(x - close_coords[0]) <= 14) and (abs(y - close_coords[1]) <= 14):
                self.toggle_expand(False)
                return

        # Check Action / Approval Chips
        if self.chip_approve_bbox and (self.chip_approve_bbox[0] <= x <= self.chip_approve_bbox[2] and self.chip_approve_bbox[1] <= y <= self.chip_approve_bbox[3]):
            self._on_approve_click()
            return
        if self.chip_deny_bbox and (self.chip_deny_bbox[0] <= x <= self.chip_deny_bbox[2] and self.chip_deny_bbox[1] <= y <= self.chip_deny_bbox[3]):
            self._on_deny_click()
            return

        # Check Mic button
        if hasattr(self, "_btn_mic_cx") and hasattr(self, "_btn_mic_cy"):
            if (x - self._btn_mic_cx) ** 2 + (y - self._btn_mic_cy) ** 2 <= 16 ** 2:
                self.on_mic_click()
                return

        # Check Send button
        if hasattr(self, "_btn_send_cx") and hasattr(self, "_btn_send_cy"):
            if (x - self._btn_send_cx) ** 2 + (y - self._btn_send_cy) ** 2 <= 16 ** 2:
                self.on_send()
                return

        # If speaking, clicking speech area cuts off audio
        if getattr(self, "is_speaking", False) and y > 48:
            if hasattr(self.asst, "speaker") and self.asst.speaker:
                self.asst.speaker.stop()
            self.is_speaking = False
            self._reset_status()
            return


def launch_widget(asst: Assistant | None = None):
    load_env(HERE / ".env")

    if asst is None:
        from audio import ConsoleSpeaker, Speaker
        backend = os.environ.get("TTS_BACKEND", "fish_audio").lower().strip()
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
            model=os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
            name=name,
        )
        names = ["jarvis", "assistant"]
        asst = Assistant(speaker, apps, llm, names, dry_run=False)

    app = JarvisIslandWidget(asst)
    app.root.mainloop()


# Backward compatibility alias
TwoCodeIslandWidget = JarvisIslandWidget
DynamicIslandWidget = JarvisIslandWidget


if __name__ == "__main__":
    launch_widget()
