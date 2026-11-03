"""Proactive ambient monitoring and Stark System Alerts for Jarvis."""
from __future__ import annotations

import datetime
import os
import re
import threading
import time


class ProactiveMonitor:
    """Background sentinel monitoring battery, system health, and upcoming meetings."""

    def __init__(self, speaker, check_interval: float = 30.0):
        self.speaker = speaker
        self.check_interval = check_interval
        self._running = False
        self._thread: threading.Thread | None = None

        # State tracking to avoid repetitive alerts
        self._low_battery_alerted = False
        self._high_load_alerted = False
        self._alerted_events: set[str] = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ProactiveMonitor")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        # Initial settle time so startup greetings / daily briefing happen first
        time.sleep(5.0)

        while self._running:
            try:
                self._check_battery()
                self._check_system_load()
                self._check_upcoming_events()
            except Exception as e:
                pass
            time.sleep(self.check_interval)

    def _check_battery(self):
        try:
            import psutil
            batt = psutil.sensors_battery()
            if not batt:
                return

            percent = round(batt.percent)
            plugged = batt.power_plugged

            if plugged or percent > 28:
                self._low_battery_alerted = False
            elif percent <= 25 and not self._low_battery_alerted:
                self._low_battery_alerted = True
                self.speaker.speak(
                    f"Pardon the interruption, sir: battery reserves have reached {percent} percent. "
                    "I suggest plugging in the charger now."
                )
        except Exception:
            pass

    def _check_system_load(self):
        try:
            import psutil
            mem = psutil.virtual_memory().percent
            if mem > 93:
                if not self._high_load_alerted:
                    self._high_load_alerted = True
                    self.speaker.speak(
                        f"Notice, sir: system memory load is elevated at {int(mem)} percent."
                    )
            elif mem < 80:
                self._high_load_alerted = False
        except Exception:
            pass

    def _check_upcoming_events(self):
        try:
            from actions import fetch_calendar_events
            events = fetch_calendar_events()
            if not events:
                return

            now = datetime.datetime.now()
            today_str = now.strftime("%Y%m%d")

            for ev in events:
                # Match events like "Meeting with Team at 3:30 PM"
                m = re.search(r"^(.+?)\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)$", ev, re.IGNORECASE)
                if not m:
                    continue

                title = m.group(1).strip()
                hh = int(m.group(2))
                mm = int(m.group(3))
                period = m.group(4).upper()

                if period == "PM" and hh != 12:
                    hh += 12
                elif period == "AM" and hh == 12:
                    hh = 0

                event_time = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                diff_sec = (event_time - now).total_seconds()
                diff_min = round(diff_sec / 60)

                event_key = f"{today_str}_{title}_{hh}_{mm}"
                if 5 <= diff_min <= 15 and event_key not in self._alerted_events:
                    self._alerted_events.add(event_key)
                    self.speaker.speak(
                        f"Sir, pardon the interruption: your {title} is scheduled to begin in {diff_min} minutes."
                    )
        except Exception:
            pass
