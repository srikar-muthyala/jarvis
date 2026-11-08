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
    """Generate authentic macOS-style Frosted Glass container and card grid with sub-pixel antialiasing."""
    # 4x internal supersampling for pristine antialiasing and sub-pixel edge clarity
    ss = 4
    sw, sh = max(8, w * ss), max(8, h * ss)

    pad = 2 * ss
    x1, y1 = pad, pad
    x2, y2 = sw - pad, sh - pad

    # Pure capsule pill in compact mode (radius = height / 2)
    radius = min(sw // 2, sh // 2) if not expanded else 22 * ss

    # Master canvas initialized with transparent colorkey (RGB 1, 1, 1)
    img = Image.new("RGBA", (sw, sh), (1, 1, 1, 255))

    # 1. Base Glass Material
    glass_surface = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(glass_surface)

    if not expanded:
        # COMPACT MODE: Apple Dynamic Island Obsidian Glass Capsule
        # Deep lustrous obsidian black with soft top light refraction (ZERO diagonal slashes)
        for y in range(sh):
            t = y / max(1, sh - 1)
            v = int(14 * (1.0 - t))
            r = 11 + v
            g = 13 + v
            b = 19 + v
            sdraw.line([(0, y), (sw, y)], fill=(r, g, b, 255))
    else:
        # EXPANDED MODE: Deep Dark Obsidian Container
        for y in range(sh):
            t = y / max(1, sh - 1)
            r = int(14 + (8 - 14) * t)
            g = int(18 + (10 - 18) * t)
            b = int(28 + (16 - 28) * t)
            sdraw.line([(0, y), (sw, y)], fill=(r, g, b, 255))

    # Clean antialiased mask
    mask = Image.new("L", (sw, sh), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=255)

    # Composite glass surface onto master canvas through mask
    img.paste(glass_surface, (0, 0), mask)
    draw = ImageDraw.Draw(img)

    # 2. Specular Bevel & Mac Glass Perimeter Edge
    rim_alpha = 32 if not expanded else 28
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=(255, 255, 255, rim_alpha), width=max(1, ss))

    # Top Edge Specular Gleam (soft horizontal light reflection on upper bezel)
    gleam_inset = radius + 4 * ss
    if x2 - gleam_inset > x1 + gleam_inset:
        gleam_alpha = 95 if not expanded else 80
        draw.line([(x1 + gleam_inset, y1 + ss), (x2 - gleam_inset, y1 + ss)],
                  fill=(255, 255, 255, gleam_alpha), width=max(1, ss))
        draw.line([(x1 + gleam_inset + 4 * ss, y1 + 2 * ss), (x2 - gleam_inset - 4 * ss, y1 + 2 * ss)],
                  fill=(255, 255, 255, gleam_alpha // 2), width=max(1, ss))

    # 3. EXPANDED MODE: Distinct Frosted Glass Tiles with Visible Depth & Contrast
    if expanded and sw >= 220 * ss:
        top_bar_h = 32 * ss
        bot_margin = 14 * ss
        left_w = int(sw * 0.58)
        left_h = max(20 * ss, sh - top_bar_h - bot_margin)
        card_r = 16 * ss

        card_bg = (30, 38, 58, 255)
        card_rim = (255, 255, 255, 32)
        card_gleam = (255, 255, 255, 75)

        # Left Card (AI Assistant)
        lx1, ly1 = 14 * ss, top_bar_h
        lx2, ly2 = 14 * ss + left_w, top_bar_h + left_h
        draw.rounded_rectangle([lx1, ly1, lx2, ly2], radius=card_r, fill=card_bg, outline=card_rim, width=ss)
        draw.line([(lx1 + card_r, ly1 + ss), (lx2 - card_r, ly1 + ss)], fill=card_gleam, width=ss)

        # Right Cards Column
        right_x = 14 * ss + left_w + 12 * ss
        right_w = sw - right_x - 14 * ss
        if right_w > 10 * ss and left_h > 20 * ss:
            gap = 10 * ss
            rc_h = max(10 * ss, (left_h - gap) // 2)

            # Right Card 1 (Now Playing / Clock & Date)
            rx1, ly1 = right_x, top_bar_h
            rx2, ry2 = right_x + right_w, top_bar_h + rc_h
            draw.rounded_rectangle([rx1, ly1, rx2, ry2], radius=card_r, fill=card_bg, outline=card_rim, width=ss)
            draw.line([(rx1 + card_r, ly1 + ss), (rx2 - card_r, ly1 + ss)], fill=card_gleam, width=ss)

            # Right Card 2 (Battery & System Telemetry)
            rc2_y = top_bar_h + rc_h + gap
            rx2_1, ry2_1 = right_x, rc2_y
            rx2_2, ry2_2 = right_x + right_w, top_bar_h + left_h
            draw.rounded_rectangle([rx2_1, ry2_1, rx2_2, ry2_2], radius=card_r, fill=card_bg, outline=card_rim, width=ss)
            draw.line([(rx2_1 + card_r, ry2_1 + ss), (rx2_2 - card_r, ry2_1 + ss)], fill=card_gleam, width=ss)

    # Downsample with high-fidelity Lanczos filter
    final_img = img.resize((w, h), Image.Resampling.LANCZOS)

    # Clean colorkey boundary: snap near-colorkey fringe pixels to exact (1, 1, 1)
    # This prevents Windows DWM from rendering ugly black staircase fringes around curved edges
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

        # Island Dimensions
        self.W_COMPACT = 118
        self.W_COMPACT_WAVE = 176
        self.H_COMPACT = 40
        self.W_EXPANDED = 650
        self.H_EXPANDED = 230
        self.H_REPLY_EXTRA = 60

        # Fixed Window Container Dimensions (never resized during animation ticks)
        self.WIN_W = 680
        self.WIN_H = 340

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
            self.root.wm_attributes("-alpha", 0.94)
        except Exception:
            pass

        self.root.geometry(f"{self.WIN_W}x{self.WIN_H}+{self.win_x}+{self.win_y}")
        self.root.update_idletasks()

        # Windows 11 DWM Immersive Dark Mode & Native Rounded Corners
        try:
            import ctypes
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            hwnd = user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()

            # 1. Dark Mode
            dark = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))

            # 2. Windows 11 DWM Rounded Window Corners (2 = DWMWCP_ROUND)
            corner_pref = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
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

        # Unified Chat Entry Frame (Mac Frosted Glass Inset)
        self.input_frame = tk.Frame(self.canvas, bg="#1e263a")
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            self.input_frame,
            textvariable=self.entry_var,
            bg="#1e263a",
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

        # Scrollable Reply Area (Mac Frosted Glass Inset)
        self.reply_frame = tk.Frame(self.canvas, bg="#1e263a")
        self.reply_text = tk.Text(
            self.reply_frame,
            bg="#1e263a",
            fg="#e2e8f0",
            font=("Segoe UI", 9),
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="arrow",
            selectbackground="#262626",
            selectforeground="#f5f5f5"
        )
        self.reply_text.pack(fill="both", expand=True)
        self.reply_text.bind("<MouseWheel>", self._on_reply_scroll)
        self.reply_text.bind("<Button-4>", lambda e: self.reply_text.yview_scroll(-2, "units"))
        self.reply_text.bind("<Button-5>", lambda e: self.reply_text.yview_scroll(2, "units"))
        self.reply_text.bind("<Button-1>", self._on_reply_click)
        self._last_rendered_reply = None

        # Fonts for dynamic metrics
        self.font_chip_bold = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.font_chip_norm = tkfont.Font(family="Segoe UI", size=8)
        self.font_clock = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.font_compact_title = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        self.font_compact_status = tkfont.Font(family="Segoe UI", size=7)

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

        # 2. Compact Notch Mascot, Title & Dynamic Audio Waveform
        self.item_compact_robo = self.canvas.create_image(0, 0, tags="btn_notch")
        self.item_compact_title = self.canvas.create_text(0, 0, anchor="w", text="J.A.R.V.I.S.", font=self.font_compact_title, fill="#f5f5f5", state="hidden", tags="btn_notch")
        self.item_compact_status = self.canvas.create_text(0, 0, anchor="w", text="● Ready", font=self.font_compact_status, fill="#a3a3a3", state="hidden", tags="btn_notch")
        self.item_wave_bar1 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden", tags="btn_notch")
        self.item_wave_bar2 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden", tags="btn_notch")
        self.item_wave_bar3 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden", tags="btn_notch")
        self.item_wave_bar4 = self.canvas.create_polygon(0, 0, 0, 0, fill="#10b981", state="hidden", tags="btn_notch")
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

        # 4. Left AI Assistant Card
        self.item_agent_robo = self.canvas.create_image(0, 0, tags="btn_robo", state="hidden")
        self.canvas.tag_bind("btn_robo", "<Button-1>", lambda e: self.mascot.trigger_click_wobble())
        self.item_agent_title = self.canvas.create_text(0, 0, anchor="w", text="Jarvis Assistant", font=("Segoe UI", 10, "bold"), fill="#f8fafc", state="hidden")
        self.item_agent_status = self.canvas.create_text(0, 0, anchor="w", text="● Ready", font=("Segoe UI", 8), fill="#94a3b8", state="hidden")

        # Input Box Outline & Icons
        self.item_input_box = self.canvas.create_polygon(0, 0, 0, 0, fill="#141926", outline="#333f5c", width=1.0, smooth=True, state="hidden")
        self.item_btn_send = self.canvas.create_text(0, 0, text="➤", font=("Segoe UI", 9), fill="#38bdf8", tags="btn_send", state="hidden")
        self.item_btn_mic = self.canvas.create_text(0, 0, text="🎙", font=("Segoe UI", 10), fill="#f8fafc", tags="btn_mic", state="hidden")

        # Reply & Output Text
        self.item_reply_text = self.canvas.create_text(0, 0, anchor="nw", text="", font=("Segoe UI", 9), fill="#e2e8f0", state="hidden")

        # Interactive Action / Approval Chips (Yes / No)
        self.item_chip_approve_bg = self.canvas.create_polygon(0, 0, 0, 0, fill="#065f46", outline="#34d399", width=1.0, smooth=True, state="hidden", tags="chip_approve")
        self.item_chip_approve_text = self.canvas.create_text(0, 0, text="✓ Yes", font=("Segoe UI", 8, "bold"), fill="#f8fafc", state="hidden", tags="chip_approve")
        self.item_chip_deny_bg = self.canvas.create_polygon(0, 0, 0, 0, fill="#1e2433", outline="#475569", width=1.0, smooth=True, state="hidden", tags="chip_deny")
        self.item_chip_deny_text = self.canvas.create_text(0, 0, text="✕ No", font=("Segoe UI", 8), fill="#94a3b8", state="hidden", tags="chip_deny")

        # 5. Right Top Card: Clock & Date
        self.item_clock_time = self.canvas.create_text(0, 0, anchor="nw", text="12", font=("Segoe UI", 15, "bold"), fill="#ffffff", state="hidden")
        self.item_clock_colon = self.canvas.create_text(0, 0, anchor="nw", text=":", font=("Segoe UI", 15, "bold"), fill="#ffffff", state="hidden")
        self.item_clock_mm = self.canvas.create_text(0, 0, anchor="nw", text="00", font=("Segoe UI", 15, "bold"), fill="#ffffff", state="hidden")
        self.item_clock_date = self.canvas.create_text(0, 0, anchor="nw", text="Mon 02 Nov", font=("Segoe UI", 8), fill="#94a3b8", state="hidden")

        # 6. Right Bottom Card: Battery & System Telemetry with Live Animated Micro-Gauges
        self.item_bolt_glow = self.canvas.create_polygon(0, 0, 0, 0, fill="#14532d", state="hidden")
        self.item_bolt = self.canvas.create_polygon(0, 0, 0, 0, fill="#4ade80", state="hidden")
        self.item_sys_bat = self.canvas.create_text(0, 0, anchor="nw", text="Battery", font=("Segoe UI", 9, "bold"), fill="#f8fafc", state="hidden")
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
        self.entry_var.set("Ask Jarvis...")
        self.entry.config(fg="#525252")
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
        has_approval = bool(getattr(self.asst, "pending_briefing", False) or getattr(self.asst, "pending_url", None) or getattr(self.asst, "pending_memory_cleanup", False))
        now = time.perf_counter()
        is_mic_hud = getattr(self, "hud_mic_active", False) and (now < getattr(self, "hud_mic_until", 0.0))
        is_vol_hud = getattr(self, "hud_volume_active", False) and (now < getattr(self, "hud_volume_until", 0.0))
        is_media_active = bool(getattr(self, "media_state", None) and self.media_state.is_playing and not (self.is_speaking or self.is_listening or self.is_thinking))

        if not self.expanded:
            if is_mic_hud:
                tw = 196.0
            elif is_vol_hud:
                tw = 216.0
            elif is_media_active:
                # Dynamic width bloom for media title
                try:
                    song_lbl = f"{self.media_state.title} • {self.media_state.artist}"
                    text_w = self.font_compact_title.measure(song_lbl[:26])
                    tw = max(220.0, min(310.0, 48.0 + text_w + 48.0))
                except Exception:
                    tw = 240.0
            else:
                # Dynamic horizontal bloom: 118px resting -> 176px when waveform is active (speaking or listening)
                is_active_wave = bool(self.is_speaking or (self.is_listening and self.status_label == "Listening"))
                if is_active_wave:
                    tw = float(self.W_COMPACT_WAVE)
                else:
                    # Calculate needed width for text content in compact mode
                    badge_txt = self.current_tool_badge or f"● {self.status_label}"
                    try:
                        title_w = self.font_compact_title.measure("J.A.R.V.I.S.")
                        badge_w = self.font_compact_status.measure(badge_txt)
                        needed_w = 38.0 + max(title_w, badge_w) + 18.0
                        tw = max(float(self.W_COMPACT), min(float(self.W_COMPACT_WAVE), needed_w))
                    except Exception:
                        tw = float(self.W_COMPACT)
            th = float(self.H_COMPACT)
            expanding = (tw > self.cur_w)
        else:
            tw = float(self.W_EXPANDED)
            base_h = float(self.H_EXPANDED)
            if self.last_reply and len(self.last_reply) > 100:
                base_h += 40.0
            if has_approval:
                base_h += 34.0
            th = min(320.0, base_h)
            expanding = True

        if tw != getattr(self, "target_w", None) or th != getattr(self, "target_h", None):
            self._start_transition(tw, th, is_expanding=expanding)

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
            if (island_x + w - 36 <= x <= island_x + w - 6) and (4 <= y <= 24):
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

        # Ensure input frame is mapped so Tkinter can assign keyboard focus
        island_x = (self.WIN_W - int(self.cur_w)) // 2
        island_w = int(self.cur_w)
        top_bar_h = 30
        input_y = top_bar_h + 52
        input_h = 28
        left_w = int(island_w * 0.58)
        left_x = island_x + 14
        input_w = max(60, left_w - 24)
        entry_w = max(40, input_w - 56)
        self.input_frame.place(x=left_x + 16, y=input_y + 2, width=entry_w, height=input_h - 4)

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
        self.root.geometry(f"{self.WIN_W}x{self.WIN_H}+{self.win_x}+{self.win_y}")

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

        has_approval = bool(getattr(self.asst, "pending_briefing", False) or getattr(self.asst, "pending_url", None))
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

        island_x = (self.WIN_W - w) // 2
        island_y = 10 if not self.expanded else 0

        # Background frame positioned at (island_x, island_y)
        bg_photo = self._get_bg_photo(w, h, mood, self.expanded)
        self.canvas.itemconfig(self.item_bg, image=bg_photo)
        self.canvas.coords(self.item_bg, island_x, island_y)

        # ----------------------------------------------------------------------
        # COMPACT NOTCH / ISLAND MODE
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

            # CASE A: Mic Sentinel HUD
            if is_mic_hud:
                self.canvas.itemconfig(self.item_compact_robo, state="hidden")
                self.canvas.itemconfig(self.item_compact_title, state="hidden")
                self.canvas.itemconfig(self.item_compact_status, state="hidden")
                self._hide_media_compact_items()
                self._hide_wave_items()

                self.canvas.coords(self.item_hud_icon, island_x + 22, island_y + h / 2)
                self.canvas.itemconfig(self.item_hud_icon, text="🎙️", state="normal")

                hud_txt = "MIC MUTED" if self.hud_mic_muted else "MIC ACTIVE"
                hud_color = "#ef4444" if self.hud_mic_muted else "#10b981"
                self.canvas.coords(self.item_hud_text, island_x + 40, island_y + 12)
                self.canvas.itemconfig(self.item_hud_text, text=hud_txt, fill=hud_color, state="normal")

                self.canvas.coords(self.item_hud_sub, island_x + 40, island_y + 26)
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
                self.canvas.coords(self.item_hud_icon, island_x + 22, island_y + h / 2)
                self.canvas.itemconfig(self.item_hud_icon, text=vol_icon, state="normal")

                self.canvas.coords(self.item_hud_text, island_x + 40, island_y + h / 2)
                self.canvas.itemconfig(self.item_hud_text, text=f"{self.hud_volume_val}%", fill="#f5f5f5", state="normal")

                # Horizontal Volume Bar
                bx = island_x + 78.0
                bw = max(30.0, float(w - 94.0))
                cy = island_y + h / 2
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

                # Spinning vinyl disc indicator
                cx_disc = island_x + 22.0
                cy_disc = island_y + h / 2
                self.canvas.coords(self.item_media_disc, cx_disc - 10, cy_disc - 10, cx_disc + 10, cy_disc + 10)
                self.canvas.coords(self.item_media_hole, cx_disc - 3, cy_disc - 3, cx_disc + 3, cy_disc + 3)
                self.canvas.itemconfig(self.item_media_disc, state="normal")
                self.canvas.itemconfig(self.item_media_hole, state="normal")

                # Track Title & Artist
                avail_mw = max(40, int(w) - 76)
                disp_title = self._truncate_text_to_width(self.media_state.title or "Playing", self.font_compact_title, avail_mw)
                art_lbl = f"{self.media_state.artist} • {self.media_state.source_app}" if self.media_state.artist else self.media_state.source_app
                disp_artist = self._truncate_text_to_width(art_lbl, self.font_compact_status, avail_mw)

                self.canvas.coords(self.item_media_title, island_x + 40, island_y + 12)
                self.canvas.itemconfig(self.item_media_title, text=disp_title, state="normal")

                self.canvas.coords(self.item_media_artist, island_x + 40, island_y + 26)
                self.canvas.itemconfig(self.item_media_artist, text=disp_artist, state="normal")

                # Music Equalizer Bars (pulsing vibrant Spotify green)
                eq_x = island_x + w - 24.0
                eq_bars = (self.item_media_bar1, self.item_media_bar2, self.item_media_bar3, self.item_media_bar4)
                eq_offs = (-8.0, -2.5, 3.0, 8.5)
                eq_freqs = (5.2, 7.1, 4.4, 6.6)
                eq_p_offs = (0.0, 1.4, 2.7, 4.0)

                for bar_item, off, freq, p_off in zip(eq_bars, eq_offs, eq_freqs, eq_p_offs):
                    bh = max(3.5, min(16.0, 4.0 + 11.0 * abs(math.sin(self._anim_phase * freq + p_off))))
                    pts = _rounded_rect_points(eq_x + off - 1.2, cy_disc - bh / 2, eq_x + off + 1.2, cy_disc + bh / 2, r=1.2)
                    self.canvas.coords(bar_item, pts)
                    self.canvas.itemconfig(bar_item, fill="#1db954", state="normal")

                self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
                return

            # CASE D: Default Assistant Compact Notch
            self._hide_media_compact_items()
            robo_img = self.mascot.get_photo_image(size=28, mood=mood, phase=self._anim_phase)
            self.canvas.coords(self.item_compact_robo, island_x + 20, island_y + h / 2)
            self.canvas.itemconfig(self.item_compact_robo, image=robo_img, state="normal")

            self.canvas.itemconfig(self.item_mic_indicator, state="hidden")
            is_mic_muted = bool(hasattr(self, "sys_sentinel") and self.sys_sentinel and self.sys_sentinel.get_mic_mute())

            is_active_listening = (self.is_listening and self.status_label == "Listening")
            is_active_wave = bool(is_active_listening or self.is_speaking)
            available_w = max(24, int(w) - 38 - (42 if is_active_wave else 18))

            displayed_title = self._truncate_text_to_width("J.A.R.V.I.S.", self.font_compact_title, available_w)
            self.canvas.coords(self.item_compact_title, island_x + 38, island_y + 12)
            self.canvas.itemconfig(self.item_compact_title, text=displayed_title, state="normal")

            badge_txt = self.current_tool_badge or ("🎙️ Mic Muted" if is_mic_muted else f"● {self.status_label}")
            status_clr = "#f43f5e" if is_mic_muted else self.status_color
            displayed_badge = self._truncate_text_to_width(badge_txt, self.font_compact_status, available_w)
            self.canvas.coords(self.item_compact_status, island_x + 38, island_y + 26)
            self.canvas.itemconfig(self.item_compact_status, text=displayed_badge, fill=status_clr, state="normal")

            if is_active_wave:
                cy = island_y + h / 2
                bx = island_x + w - 24.0
                wave_color = "#f43f5e" if is_active_listening else "#10b981"
                if self.is_speaking:
                    speech_mod = 0.55 + 0.35 * math.sin(self._anim_phase * 3.2) + 0.15 * math.cos(self._anim_phase * 6.5)
                    level = max(0.25, min(1.0, speech_mod))
                else:
                    level = min(1.0, max(0.15, self._smooth_audio_level * 180.0))

                c_bars = (self.item_wave_bar1, self.item_wave_bar2, self.item_wave_bar3, self.item_wave_bar4)
                c_offsets = (-9.0, -3.0, 3.0, 9.0)
                c_freqs = (4.5, 5.8, 3.9, 6.2)
                c_phases = (0.0, 1.2, 2.4, 3.6)

                for bar_item, off, freq, p_off in zip(c_bars, c_offsets, c_freqs, c_phases):
                    bh = max(3.5, min(18.0, 4.5 + 13.0 * level * abs(math.sin(self._anim_phase * freq + p_off))))
                    pts = _rounded_rect_points(bx + off - 1.25, cy - bh / 2, bx + off + 1.25, cy + bh / 2, r=1.25)
                    self.canvas.coords(bar_item, pts)
                    self.canvas.itemconfig(bar_item, fill=wave_color, state="normal")
            else:
                self._hide_wave_items()

            return

        # Hide compact notch items when expanded
        self.canvas.itemconfig(self.item_compact_robo, state="hidden")
        self.canvas.itemconfig(self.item_compact_title, state="hidden")
        self.canvas.itemconfig(self.item_compact_status, state="hidden")
        for b in (self.item_wave_bar1, self.item_wave_bar2, self.item_wave_bar3, getattr(self, "item_wave_bar4", None),
                  getattr(self, "exp_wave_bar1", None), getattr(self, "exp_wave_bar2", None),
                  getattr(self, "exp_wave_bar3", None), getattr(self, "exp_wave_bar4", None),
                  getattr(self, "exp_wave_bar5", None)):
            if b is not None:
                self.canvas.itemconfig(b, state="hidden")
        self.canvas.itemconfig(self.item_wave_bar4, state="hidden")

        # Subtle 50ms stagger delay for internal elements during expansion
        is_animating = getattr(self, "_animating", False)
        elapsed = time.perf_counter() - getattr(self, "_anim_start_time", 0.0)
        if is_animating and getattr(self, "_is_expanding", True) and elapsed < 0.050:
            self.input_frame.place_forget()
            self._hide_expanded_items()
            return

        # If collapsing, hide internal contents immediately so pill collapses cleanly
        if is_animating and not getattr(self, "_is_expanding", True):
            self.input_frame.place_forget()
            self._hide_expanded_items()
            return

        # Top Header Bar
        self.canvas.coords(self.item_header_logo, island_x + 18, island_y + 15)
        self.canvas.itemconfig(self.item_header_logo, state="normal")
        self.canvas.coords(self.item_btn_style_toggle, island_x + w - 54, island_y + 15)
        self.canvas.itemconfig(self.item_btn_style_toggle, text="🏝️" if getattr(self, "island_style", "island") == "island" else "💻", state="normal")
        self.canvas.coords(self.item_btn_min, island_x + w - 34, island_y + 15)
        self.canvas.coords(self.item_btn_close, island_x + w - 16, island_y + 15)
        self.canvas.itemconfig(self.item_btn_min, state="normal")
        self.canvas.itemconfig(self.item_btn_close, state="normal")

        # Layout Geometry
        top_bar_h = 30
        bot_margin = 12
        left_w = int(w * 0.58)
        left_x = island_x + 14
        left_h = max(20, h - top_bar_h - bot_margin)
        gap = 10

        # 1. Left Card: AI Assistant
        robo_img = self.mascot.get_photo_image(size=40, mood=mood, phase=self._anim_phase)
        self.canvas.coords(self.item_agent_robo, left_x + 24, top_bar_h + 24)
        self.canvas.itemconfig(self.item_agent_robo, image=robo_img, state="normal")

        badge_txt = self.current_tool_badge or f"● {self.status_label}"
        self.canvas.coords(self.item_agent_title, left_x + 50, top_bar_h + 16)
        self.canvas.itemconfig(self.item_agent_title, state="normal")
        self.canvas.coords(self.item_agent_status, left_x + 50, top_bar_h + 31)
        self.canvas.itemconfig(self.item_agent_status, text=badge_txt, fill=self.status_color, state="normal")

        # Dynamic Audio Waveform Equalizer in Expanded Card Header (while Speaking or Listening)
        is_active_listening = (self.is_listening and self.status_label == "Listening")
        exp_bars = (self.exp_wave_bar1, self.exp_wave_bar2, self.exp_wave_bar3, self.exp_wave_bar4, self.exp_wave_bar5)
        if self.is_speaking or is_active_listening:
            bx = left_x + left_w - 30.0
            cy = top_bar_h + 24.0
            wave_color = "#10b981" if self.is_speaking else "#f43f5e"
            if self.is_speaking:
                speech_mod = 0.55 + 0.35 * math.sin(self._anim_phase * 3.2) + 0.15 * math.cos(self._anim_phase * 6.5)
                level = max(0.25, min(1.0, speech_mod))
            else:
                level = min(1.0, max(0.15, self._smooth_audio_level * 180.0))

            offsets = (-11.0, -5.5, 0.0, 5.5, 11.0)
            freqs = (4.2, 5.8, 3.9, 6.2, 4.7)
            phase_offsets = (0.0, 1.1, 2.3, 3.4, 4.6)

            for bar_item, off, freq, p_off in zip(exp_bars, offsets, freqs, phase_offsets):
                bh = max(4.0, min(22.0, 5.0 + 16.0 * level * abs(math.sin(self._anim_phase * freq + p_off))))
                pts = _rounded_rect_points(bx + off - 1.5, cy - bh / 2, bx + off + 1.5, cy + bh / 2, r=1.5)
                self.canvas.coords(bar_item, pts)
                self.canvas.itemconfig(bar_item, fill=wave_color, state="normal")
        else:
            for bar_item in exp_bars:
                self.canvas.itemconfig(bar_item, state="hidden")

        # Input capsule inside left card
        input_y = top_bar_h + 52
        input_h = 28
        input_w = max(60, left_w - 24)
        pts_in = _rounded_rect_points(left_x + 12, input_y, left_x + 12 + input_w, input_y + input_h, r=12)
        self.canvas.coords(self.item_input_box, pts_in)
        self.canvas.itemconfig(self.item_input_box, state="normal")

        # Dynamically scale input frame
        entry_w = max(40, input_w - 56)
        self.input_frame.place(x=left_x + 16, y=input_y + 2, width=entry_w, height=input_h - 4)
        self.canvas.coords(self.item_btn_send, left_x + 12 + input_w - 38, input_y + input_h / 2)
        self.canvas.coords(self.item_btn_mic, left_x + 12 + input_w - 18, input_y + input_h / 2)
        self.canvas.itemconfig(self.item_btn_send, state="normal")
        self.canvas.itemconfig(self.item_btn_mic, state="normal")

        # Reply Area / Action Chips
        reply_y = input_y + input_h + 12
        card_bottom = top_bar_h + left_h

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

            # Equal balanced clean button widths for Yes and No
            app_w = max(68.0, self.font_chip_bold.measure(app_lbl) + 30.0)
            den_w = max(68.0, self.font_chip_norm.measure(den_lbl) + 30.0)
            chip_h = 24.0
            gap_chip = 12.0

            total_chips_w = app_w + gap_chip + den_w
            cx_card = left_x + left_w / 2
            x1_app = max(left_x + 14, cx_card - total_chips_w / 2)
            x2_app = x1_app + app_w
            x1_den = x2_app + gap_chip
            x2_den = x1_den + den_w

            chip_y = max(reply_y + 36.0, card_bottom - chip_h - 10.0)
            avail_h = max(20.0, chip_y - reply_y - 8.0)

            self.chip_approve_bbox = (int(x1_app), int(chip_y), int(x2_app), int(chip_y + chip_h))
            self.chip_deny_bbox = (int(x1_den), int(chip_y), int(x2_den), int(chip_y + chip_h))

            # Reactive 3D hover lift micro-interaction on action chips
            lift_app = 2.0 if getattr(self, "_hover_chip", None) == "approve" else 0.0
            pts_app = _rounded_rect_points(x1_app, chip_y - lift_app, x2_app, chip_y + chip_h - lift_app, r=8)
            self.canvas.coords(self.item_chip_approve_bg, pts_app)
            self.canvas.coords(self.item_chip_approve_text, (x1_app + x2_app) / 2, chip_y + chip_h / 2 - lift_app)
            app_fill = "#059669" if lift_app > 0 else "#262626"
            app_outline = "#34d399" if lift_app > 0 else "#525252"
            self.canvas.itemconfig(self.item_chip_approve_bg, fill=app_fill, outline=app_outline, state="normal")
            self.canvas.itemconfig(self.item_chip_approve_text, text=app_lbl, state="normal")

            lift_den = 2.0 if getattr(self, "_hover_chip", None) == "deny" else 0.0
            pts_den = _rounded_rect_points(x1_den, chip_y - lift_den, x2_den, chip_y + chip_h - lift_den, r=8)
            self.canvas.coords(self.item_chip_deny_bg, pts_den)
            self.canvas.coords(self.item_chip_deny_text, (x1_den + x2_den) / 2, chip_y + chip_h / 2 - lift_den)
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
            avail_h = max(20.0, card_bottom - reply_y - 10.0)

        if self.last_reply and left_w >= 100:
            clean = str(self.last_reply).replace("\x00", "").replace("\r", " ").strip()
            self._set_reply_content(clean)
            reply_w = max(60, left_w - 28)
            self.reply_frame.place(x=left_x + 14, y=reply_y, width=reply_w, height=int(avail_h))
            self.canvas.itemconfig(self.item_reply_text, state="hidden")
        else:
            if hasattr(self, "reply_frame"):
                self.reply_frame.place_forget()
            self.canvas.itemconfig(self.item_reply_text, state="hidden")

        # Right Cards Column Geometry
        right_x = left_x + left_w + gap
        right_w = (island_x + w) - right_x - 14
        rc_h = max(10, (left_h - gap) // 2)

        # 2. Right Top Card: Now Playing Media Card OR Clock & Date
        if right_w >= 40 and left_h >= 60:
            rc1_y = top_bar_h
            has_media = bool(getattr(self, "media_state", None) and self.media_state.is_active)
            if has_media:
                # Hide Clock & Date items
                self.canvas.itemconfig(self.item_clock_time, state="hidden")
                self.canvas.itemconfig(self.item_clock_colon, state="hidden")
                self.canvas.itemconfig(self.item_clock_mm, state="hidden")
                self.canvas.itemconfig(self.item_clock_date, state="hidden")

                # Show Media Card items
                src_lbl = f"● {self.media_state.source_app.upper()}"
                self.canvas.coords(self.item_mc_badge, right_x + 16, rc1_y + 10)
                self.canvas.itemconfig(self.item_mc_badge, text=src_lbl, state="normal")

                avail_mw = max(40, right_w - 90)
                disp_title = self._truncate_text_to_width(self.media_state.title or "Unknown Track", self.font_chip_bold, avail_mw)
                disp_art = self._truncate_text_to_width(self.media_state.artist or "Media Player", self.font_compact_status, avail_mw)

                self.canvas.coords(self.item_mc_title, right_x + 16, rc1_y + 26)
                self.canvas.itemconfig(self.item_mc_title, text=disp_title, state="normal")

                self.canvas.coords(self.item_mc_artist, right_x + 16, rc1_y + 44)
                self.canvas.itemconfig(self.item_mc_artist, text=disp_art, state="normal")

                # Media Playback Controls
                ctrl_y = rc1_y + 36
                self.canvas.coords(self.item_mc_prev, right_x + right_w - 60, ctrl_y)
                self.canvas.itemconfig(self.item_mc_prev, state="normal")

                play_icon = "⏸" if self.media_state.is_playing else "▶"
                self.canvas.coords(self.item_mc_play, right_x + right_w - 38, ctrl_y)
                self.canvas.itemconfig(self.item_mc_play, text=play_icon, state="normal")

                self.canvas.coords(self.item_mc_next, right_x + right_w - 16, ctrl_y)
                self.canvas.itemconfig(self.item_mc_next, state="normal")
            else:
                # Hide Media Card items
                self.canvas.itemconfig(self.item_mc_badge, state="hidden")
                self.canvas.itemconfig(self.item_mc_title, state="hidden")
                self.canvas.itemconfig(self.item_mc_artist, state="hidden")
                self.canvas.itemconfig(self.item_mc_prev, state="hidden")
                self.canvas.itemconfig(self.item_mc_play, state="hidden")
                self.canvas.itemconfig(self.item_mc_next, state="hidden")

                # Show Classic Clock & Date
                cy1 = rc1_y + rc_h / 2
                now = datetime.datetime.now()
                hh_str = now.strftime("%H")
                mm_str = now.strftime("%M")
                date_str = now.strftime("%A, %d %b")

                colon_val = int(140 + 115 * math.sin(self._anim_phase * 2.8))
                colon_fill = f"#{colon_val:02x}{colon_val:02x}{colon_val:02x}"

                hh_w = self.font_clock.measure(hh_str)
                colon_w = self.font_clock.measure(":")

                self.canvas.coords(self.item_clock_time, right_x + 16, cy1 - 12)
                self.canvas.itemconfig(self.item_clock_time, text=hh_str, fill="#f5f5f5", state="normal")

                self.canvas.coords(self.item_clock_colon, right_x + 16 + hh_w, cy1 - 12)
                self.canvas.itemconfig(self.item_clock_colon, text=":", fill=colon_fill, state="normal")

                self.canvas.coords(self.item_clock_mm, right_x + 16 + hh_w + colon_w, cy1 - 12)
                self.canvas.itemconfig(self.item_clock_mm, text=mm_str, fill="#f5f5f5", state="normal")

                self.canvas.coords(self.item_clock_date, right_x + 16, cy1 + 12)
                self.canvas.itemconfig(self.item_clock_date, text=date_str, fill="#a3a3a3", state="normal")

            # 3. Right Bottom Card: Battery & System Telemetry with Live Animated Micro-Gauges
            rc2_y = top_bar_h + rc_h + gap
            rc2_h = (top_bar_h + left_h) - rc2_y

            # Clean vertical spacing: Battery near top of card, CPU and RAM below with clear separation
            y_bat = rc2_y + 11.0
            y_cpu = rc2_y + 36.0
            y_ram = rc2_y + 53.0

            # Battery status & user-provided SVG charging bolt animation
            bat_str = self.telemetry.get("bat", "AC Power")
            is_charging = "Charging" in bat_str or "Plugged" in bat_str

            # Compact proportional bolt geometry: 9px wide x 14px tall
            bw, bh = 9.0, 14.0
            bx = right_x + 16.0
            by = y_bat + 1.0

            pts_bolt = [
                bx + 0.632 * bw, by + 0.000 * bh,
                bx + 0.000 * bw, by + 0.514 * bh,
                bx + 0.368 * bw, by + 0.595 * bh,
                bx + 0.368 * bw, by + 1.000 * bh,
                bx + 1.000 * bw, by + 0.459 * bh,
                bx + 0.632 * bw, by + 0.405 * bh,
            ]

            if is_charging:
                # Smooth breathing cycle (sine wave)
                t_breathe = 0.5 + 0.5 * math.sin(self._anim_phase * 2.4)
                # Pulse between user SVG lime green (#6bb13f) and high-energy neon green (#4ade80)
                r_c = int(74 + (107 - 74) * (1.0 - t_breathe))
                g_c = int(177 + (222 - 177) * t_breathe)
                b_c = int(48 + (128 - 48) * t_breathe)
                bolt_color = f"#{r_c:02x}{g_c:02x}{b_c:02x}"

                # Subtle ambient aura behind the bolt
                glow_pad = 1.5
                gbw, gbh = bw + glow_pad * 2, bh + glow_pad * 2
                gbx, gby = bx - glow_pad, by - glow_pad
                pts_glow = [
                    gbx + 0.632 * gbw, gby + 0.000 * gbh,
                    gbx + 0.000 * gbw, gby + 0.514 * gbh,
                    gbx + 0.368 * gbw, gby + 0.595 * gbh,
                    gbx + 0.368 * gbw, gby + 1.000 * gbh,
                    gbx + 1.000 * gbw, gby + 0.459 * gbh,
                    gbx + 0.632 * gbw, gby + 0.405 * gbh,
                ]
                self.canvas.coords(self.item_bolt_glow, pts_glow)
                self.canvas.itemconfig(self.item_bolt_glow, fill="#14532d", state="normal")
                bat_text_color = "#f5f5f5"
            else:
                self.canvas.itemconfig(self.item_bolt_glow, state="hidden")
                if "Low" in bat_str or "Critical" in bat_str:
                    bolt_color = "#f43f5e"
                    bat_text_color = "#f43f5e"
                else:
                    bolt_color = "#a3a3a3"
                    bat_text_color = "#e5e5e5"

            self.canvas.coords(self.item_bolt, pts_bolt)
            self.canvas.itemconfig(self.item_bolt, fill=bolt_color, state="normal")

            self.canvas.coords(self.item_sys_bat, bx + bw + 8, y_bat)
            self.canvas.itemconfig(self.item_sys_bat, text=bat_str, fill=bat_text_color, state="normal")

            # CPU & RAM micro-meter geometry
            bar_track_w = max(30.0, float(right_w - 95))
            bar_x = right_x + 78.0

            # CPU
            cpu_val = max(0.0, min(100.0, self._cur_cpu_pct))
            cpu_fill_w = max(3.0, (cpu_val / 100.0) * bar_track_w)
            cpu_color = "#f43f5e" if cpu_val > 85.0 else ("#f59e0b" if cpu_val > 70.0 else "#38bdf8")

            self.canvas.coords(self.item_cpu_lbl, right_x + 16, y_cpu - 6)
            self.canvas.itemconfig(self.item_cpu_lbl, text=f"CPU {cpu_val:.0f}%", fill="#94a3b8", state="normal")

            pts_cpu_tr = _rounded_rect_points(bar_x, y_cpu - 2, bar_x + bar_track_w, y_cpu + 2, r=2)
            self.canvas.coords(self.item_cpu_track, pts_cpu_tr)
            self.canvas.itemconfig(self.item_cpu_track, fill="#1e2433", state="normal")

            pts_cpu_fl = _rounded_rect_points(bar_x, y_cpu - 2, bar_x + cpu_fill_w, y_cpu + 2, r=2)
            self.canvas.coords(self.item_cpu_fill, pts_cpu_fl)
            self.canvas.itemconfig(self.item_cpu_fill, fill=cpu_color, state="normal")

            # RAM
            ram_val = max(0.0, min(100.0, self._cur_ram_pct))
            ram_fill_w = max(3.0, (ram_val / 100.0) * bar_track_w)
            ram_color = "#f43f5e" if ram_val > 85.0 else ("#f59e0b" if ram_val > 75.0 else "#f59e0b")

            self.canvas.coords(self.item_ram_lbl, right_x + 16, y_ram - 6)
            self.canvas.itemconfig(self.item_ram_lbl, text=f"RAM {ram_val:.0f}%", fill="#94a3b8", state="normal")

            pts_ram_tr = _rounded_rect_points(bar_x, y_ram - 2, bar_x + bar_track_w, y_ram + 2, r=2)
            self.canvas.coords(self.item_ram_track, pts_ram_tr)
            self.canvas.itemconfig(self.item_ram_track, fill="#1e2433", state="normal")

            pts_ram_fl = _rounded_rect_points(bar_x, y_ram - 2, bar_x + ram_fill_w, y_ram + 2, r=2)
            self.canvas.coords(self.item_ram_fill, pts_ram_fl)
            self.canvas.itemconfig(self.item_ram_fill, fill=ram_color, state="normal")
        else:
            self.canvas.itemconfig(self.item_clock_time, state="hidden")
            self.canvas.itemconfig(self.item_clock_colon, state="hidden")
            self.canvas.itemconfig(self.item_clock_mm, state="hidden")
            self.canvas.itemconfig(self.item_clock_date, state="hidden")
            self.canvas.itemconfig(self.item_bolt_glow, state="hidden")
            self.canvas.itemconfig(self.item_bolt, state="hidden")
            self.canvas.itemconfig(self.item_sys_bat, state="hidden")
            self.canvas.itemconfig(self.item_cpu_lbl, state="hidden")
            self.canvas.itemconfig(self.item_cpu_track, state="hidden")
            self.canvas.itemconfig(self.item_cpu_fill, state="hidden")
            self.canvas.itemconfig(self.item_ram_lbl, state="hidden")
            self.canvas.itemconfig(self.item_ram_track, state="hidden")
            self.canvas.itemconfig(self.item_ram_fill, state="hidden")

    def _hide_expanded_items(self):
        if hasattr(self, "reply_frame"):
            self.reply_frame.place_forget()
        self.canvas.itemconfig(self.item_header_logo, state="hidden")
        self.canvas.itemconfig(self.item_btn_min, state="hidden")
        self.canvas.itemconfig(self.item_btn_close, state="hidden")
        self.canvas.itemconfig(self.item_agent_robo, state="hidden")
        self.canvas.itemconfig(self.item_agent_title, state="hidden")
        self.canvas.itemconfig(self.item_agent_status, state="hidden")
        self.canvas.itemconfig(self.item_input_box, state="hidden")
        self.canvas.itemconfig(self.item_btn_send, state="hidden")
        self.canvas.itemconfig(self.item_btn_mic, state="hidden")
        self.canvas.itemconfig(self.item_reply_text, state="hidden")
        self.canvas.itemconfig(self.item_chip_approve_bg, state="hidden")
        self.canvas.itemconfig(self.item_chip_approve_text, state="hidden")
        self.canvas.itemconfig(self.item_chip_deny_bg, state="hidden")
        self.canvas.itemconfig(self.item_chip_deny_text, state="hidden")
        self.canvas.itemconfig(self.item_clock_time, state="hidden")
        self.canvas.itemconfig(self.item_clock_colon, state="hidden")
        self.canvas.itemconfig(self.item_clock_mm, state="hidden")
        self.canvas.itemconfig(self.item_clock_date, state="hidden")
        self.canvas.itemconfig(self.item_bolt_glow, state="hidden")
        self.canvas.itemconfig(self.item_bolt, state="hidden")
        self.canvas.itemconfig(self.item_sys_bat, state="hidden")
        self.canvas.itemconfig(self.item_cpu_lbl, state="hidden")
        self.canvas.itemconfig(self.item_cpu_track, state="hidden")
        self.canvas.itemconfig(self.item_cpu_fill, state="hidden")
        self.canvas.itemconfig(self.item_ram_lbl, state="hidden")
        self.canvas.itemconfig(self.item_ram_track, state="hidden")
        self.canvas.itemconfig(self.item_ram_fill, state="hidden")
        self.canvas.itemconfig(self.item_wave_bar1, state="hidden")
        self.canvas.itemconfig(self.item_wave_bar2, state="hidden")
        self.canvas.itemconfig(self.item_wave_bar3, state="hidden")
        if hasattr(self, "item_wave_bar4"):
            self.canvas.itemconfig(self.item_wave_bar4, state="hidden")
        for b in (getattr(self, "exp_wave_bar1", None), getattr(self, "exp_wave_bar2", None),
                  getattr(self, "exp_wave_bar3", None), getattr(self, "exp_wave_bar4", None),
                  getattr(self, "exp_wave_bar5", None)):
            if b is not None:
                self.canvas.itemconfig(b, state="hidden")
        self.chip_approve_bbox = None
        self.chip_deny_bbox = None
        for item in (
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
        w = int(self.cur_w)
        h = int(self.cur_h)
        island_x = (self.WIN_W - w) // 2

        # Any user click locks the widget open
        self.hover_expanded = False

        # Click outside the island
        if not (island_x <= x <= island_x + w and 0 <= y <= h):
            if self.expanded:
                self.toggle_expand(False)
            return

        # Check Action / Approval Chips
        if self.chip_approve_bbox and (self.chip_approve_bbox[0] <= x <= self.chip_approve_bbox[2] and self.chip_approve_bbox[1] <= y <= self.chip_approve_bbox[3]):
            self._on_approve_click()
            return
        if self.chip_deny_bbox and (self.chip_deny_bbox[0] <= x <= self.chip_deny_bbox[2] and self.chip_deny_bbox[1] <= y <= self.chip_deny_bbox[3]):
            self._on_deny_click()
            return

        if not self.expanded:
            self.toggle_expand(True)
            return

        # Check Style Toggle Button (Island vs Notch)
        if (island_x + w - 66 <= x <= island_x + w - 46) and (4 <= y <= 26):
            self.toggle_island_style()
            return

        # Check Minimize Button (—)
        if (island_x + w - 44 <= x <= island_x + w - 24) and (4 <= y <= 26):
            self.toggle_expand(False)
            return

        # Check Close Button (✕)
        if (island_x + w - 24 <= x <= island_x + w - 4) and (4 <= y <= 26):
            self.toggle_expand(False)
            return

        # Check Media Card Playback Controls in Right Card 1
        has_media = bool(getattr(self, "media_state", None) and self.media_state.is_active)
        if has_media:
            left_w = int(w * 0.58)
            left_x = island_x + 14
            gap = 10
            right_x = left_x + left_w + gap
            right_w = (island_x + w) - right_x - 14
            ctrl_y = 30 + 36
            if (abs(x - (right_x + right_w - 60)) <= 12) and (abs(y - ctrl_y) <= 12):
                self._on_media_prev()
                return
            if (abs(x - (right_x + right_w - 38)) <= 12) and (abs(y - ctrl_y) <= 12):
                self._on_media_toggle()
                return
            if (abs(x - (right_x + right_w - 16)) <= 12) and (abs(y - ctrl_y) <= 12):
                self._on_media_next()
                return

        # Check Mic button
        left_w = int(w * 0.58)
        left_x = island_x + 14
        input_y = 30 + 52
        input_w = max(60, left_w - 24)
        mic_cx = left_x + 12 + input_w - 18
        if (x - mic_cx) ** 2 + (y - (input_y + 14)) ** 2 <= 14 ** 2:
            self.on_mic_click()
            return

        # Check Send button
        send_cx = left_x + 12 + input_w - 38
        if (x - send_cx) ** 2 + (y - (input_y + 14)) ** 2 <= 14 ** 2:
            self.on_send()
            return

        # If speaking, clicking speech area cuts off audio
        if getattr(self, "is_speaking", False) and y > input_y + 28:
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
