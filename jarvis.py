#!/usr/bin/env python3
"""A Jarvis-style voice & text assistant for Windows.

    python jarvis.py                  say "Hey Jarvis, open Chrome"  (always listening)
    python jarvis.py --chat           interactive text chat mode (type and chat!)
    python jarvis.py --ptt            hold push-to-talk key (default: right Ctrl), speak, release
    python jarvis.py --text "open notepad and set a timer for 5 minutes"
    python jarvis.py --text "..." --dry-run     show what would happen without doing it
    python jarvis.py --test-mic       live visual microphone meter to test voice levels
    python jarvis.py --list-mics      list microphones
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import webbrowser
from pathlib import Path

from actions import Context, TimerManager, execute
from commands import load_apps, normalize, parse, strip_wake
from proactive_monitor import ProactiveMonitor

HERE = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    """Tiny .env reader. Real environment variables win over the file."""
    # Ensure Hugging Face fixes are set before any huggingface imports
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            k = key.strip()
            v = value.strip().strip('"').strip("'")
            if k not in os.environ or (not os.environ[k] and v):
                os.environ[k] = v


def beep(freq: int = 880, ms: int = 120) -> None:
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


class Assistant:
    def __init__(self, speaker, apps, llm, names, dry_run=False):
        self.speaker, self.llm, self.names = speaker, llm, names
        self.timers = TimerManager(self._timer_done)
        self.ctx = Context(apps, self.timers, dry_run, names, llm=self.llm, speaker=self.speaker)
        self.pending_url: str | None = None
        self.pending_label: str | None = None
        self.pending_briefing: bool = False
        if not dry_run:
            self.monitor = ProactiveMonitor(self.speaker)
            self.monitor.start()
        else:
            self.monitor = None

    def check_daily_briefing_prompt(self) -> bool:
        """Check if today is the first run of the day, and offer daily briefing."""
        import datetime
        import json

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        state_file = HERE / ".daily_briefing.json"

        last_date = ""
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                last_date = data.get("last_prompt_date", "")
            except Exception:
                pass

        if last_date != today_str:
            try:
                state_file.write_text(json.dumps({"last_prompt_date": today_str}), encoding="utf-8")
            except Exception:
                pass

            self.pending_briefing = True
            prompt_msg = "Good morning, sir. Would you like me to start with today's briefing?"
            self.speaker.speak(prompt_msg)
            return True
        return False

    def _timer_done(self, message: str) -> None:
        for _ in range(3):
            beep(1000, 180)
        self.speaker.speak(message)

    def _speak_reply(self, reply: str) -> None:
        """Speak reply and scan for documentation URLs to offer opening them."""
        if not reply:
            return

        # If Jarvis is already actively opening/launching something, do NOT prompt to open it
        if re.search(r"\b(?:opening|launching|navigating to|visiting|starting|opened|launched)\b", reply, re.IGNORECASE):
            self.pending_url = None
            self.pending_label = None
            self.speaker.speak(reply)
            return

        m = re.search(
            r"\b((?:https?://)?(?:[a-zA-Z0-9-]+\.)+(?:io|com|org|net|ai|dev|app|co|in|edu|gov|me|info)(?:/[^\s,!?\"')\]]*)?)\b",
            reply,
            re.IGNORECASE
        )
        if m:
            raw_url = m.group(1).rstrip(".")
            domain = re.sub(r"^https?://", "", raw_url).split("/")[0]
            full_url = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
            self.pending_url = full_url
            self.pending_label = domain

            already_asks = bool(re.search(
                r"(?:open (?:the |that )?(?:link|website|page|site|url)|shall i open|would you like me to open)",
                reply,
                re.IGNORECASE
            ))
            if not already_asks:
                reply = f"{reply.rstrip('.')} . Would you like me to open that link for you, sir?"

        self.speaker.speak(reply)

    def handle(self, text: str) -> bool:
        """Run one command or answer one question. Returns False to quit."""
        text = normalize(text)
        if not text:
            return True
        self.ctx.last_query = text

        # Instant voice barge-in / speech cut-off
        if re.match(r"^(?:(?:hey\s+|hi\s+)?(?:jarvis|assistant)\s+)?(?:please\s+)?(?:stop|shut\s+up|be\s+quiet|quiet|silence|shh|pause|cancel|halt)$", text.strip(), re.IGNORECASE):
            self.speaker.stop()
            return True

        # Check for pending link confirmation (e.g. "yes", "open it", "sure", "no")
        if self.pending_url:
            raw_t = text.lower().strip()
            is_yes = bool(re.match(r"^(?:yes|yeah|yep|sure|ok|okay|please|yes please|please do|do it|open it|open that|open the link|open link|go ahead|proceed|yup|affirmative|yes open it)$", raw_t))
            is_no = bool(re.match(r"^(?:no|nope|nah|cancel|never mind|don't|no thanks|negative)$", raw_t))

            if is_yes:
                target_url = self.pending_url
                label = self.pending_label or target_url
                self.pending_url = None
                self.pending_label = None
                import webbrowser
                webbrowser.open(target_url)
                self.speaker.speak(f"Opening {label} now, sir.")
                return True
            elif is_no:
                self.pending_url = None
                self.pending_label = None
                self.speaker.stop()
                self.speaker.speak("Very well, sir.")
                return True
            else:
                self.pending_url = None
                self.pending_label = None

        # Check for pending daily briefing confirmation
        if getattr(self, "pending_briefing", False):
            raw_t = text.lower().strip()
            is_yes = bool(re.match(
                r"^(?:yes|yeah|yep|sure|ok|okay|please|yes please|please do|do it|start|start it|go ahead|proceed|yup|affirmative|yes start|yes please do|brief me|start today|start briefing|start my day)$",
                raw_t
            ))
            is_no = bool(re.match(
                r"^(?:no|nope|nah|cancel|never mind|don't|not now|later|no thanks|negative)$",
                raw_t
            ))

            if is_yes:
                self.pending_briefing = False
                from actions import h_daily_digest
                reply = h_daily_digest({"skip_greeting": True}, self.ctx)
                self._speak_reply(reply)
                return True
            elif is_no:
                self.pending_briefing = False
                self.speaker.speak("Very well, sir. Let me know whenever you need anything.")
                return True
            else:
                self.pending_briefing = False

        # Quick greetings - instant, polite, zero network latency
        if text in ("hey jarvis", "hi jarvis", "hello jarvis", "jarvis", "hello", "hi", "hey"):
            from actions import _pick
            self.speaker.speak(_pick("At your service, sir.", "Yes, sir?", "How may I assist you, sir?", "Always a pleasure, sir."))
            return True

        actions = parse(text, self.names)

        # Ensure that open_app actions refer to recognized apps; complex/unrecognized requests go to the LLM agent
        valid_local = bool(actions)
        if actions:
            from commands import resolve_app
            for a in actions:
                if a.kind == "open_app":
                    app_res = resolve_app(a.arg, self.ctx.apps)
                    if app_res is None and len(a.arg.split()) > 1:
                        valid_local = False
                        break

        if valid_local:
            replies = [execute(a, self.ctx) for a in actions]
            self._speak_reply(" ".join(r for r in replies if r))
        elif len(text.split()) >= 1:
            reply = self.llm.agent_run(text, self.ctx)
            self._speak_reply(reply)
        else:
            self.speaker.speak("Sorry, I didn't catch that.")
        return not self.ctx.quit


def run_chat(asst: Assistant) -> None:
    """Continuous text chat REPL with Jarvis."""
    name = asst.names[0].title()
    print("\n" + "=" * 55)
    print(f"  {name} Interactive Chat Mode")
    print("  Type any command or question. Type 'exit' to quit.")
    print("=" * 55 + "\n")

    while True:
        try:
            line = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{name}: Goodbye!")
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q", "bye"):
            print(f"{name}: Goodbye!")
            break
        if not asst.handle(line):
            break


def run_voice(asst: Assistant, wake_words, ptt: bool, ptt_key: str) -> None:
    from audio import NOISE_PHRASES, Listener, Transcriber

    print("Loading the speech model...")
    transcribe = Transcriber(
        model=os.environ.get("WHISPER_MODEL", "base.en"),
        device=os.environ.get("WHISPER_DEVICE", "cpu"),
        compute_type=os.environ.get("WHISPER_COMPUTE", "int8"),
        language=os.environ.get("WHISPER_LANGUAGE", "en") or None,
    )
    mic = os.environ.get("MIC_DEVICE", "").strip()
    listener = Listener(device=int(mic) if mic.isdigit() else (mic or None))
    listener.start()
    print("Calibrating mic (stay quiet for a second)...")
    listener.calibrate()
    asst.speaker.after = listener.flush

    def heard_text(audio) -> str:
        text = transcribe(audio)
        if text:
            print(f"heard: {text}")
        return "" if normalize(text) in NOISE_PHRASES else text

    if ptt:
        import keyboard
        asst.speaker.speak(f"Ready. Hold {ptt_key} to talk.")
        while True:
            keyboard.wait(ptt_key)
            audio = listener.record_while(lambda: keyboard.is_pressed(ptt_key))
            if audio is not None and not asst.handle(heard_text(audio)):
                return
    else:
        asst.speaker.speak(f"Ready. Say {wake_words[0]}.")
        while True:
            audio = listener.listen_phrase()
            if audio is None:
                continue
            command = strip_wake(heard_text(audio), wake_words)
            if command is None:
                continue
            if command == "":  # only the wake word: wait for the command
                beep()
                audio = listener.listen_phrase(start_timeout=6)
                if audio is None:
                    continue
                command = heard_text(audio)
            if not asst.handle(command):
                return


def main() -> None:
    ap = argparse.ArgumentParser(description="Jarvis-style voice & text assistant for Windows")
    ap.add_argument("--chat", "-c", action="store_true", help="start interactive text chat session")
    ap.add_argument("--widget", "-w", "--island", action="store_true", help="launch Dynamic Island floating desktop widget")
    ap.add_argument("--ptt", action="store_true", help="push-to-talk instead of a wake word")
    ap.add_argument("--text", help="run one command or question as text and exit")
    ap.add_argument("--no-voice", action="store_true", help="mute speech synthesis (text-only output)")
    ap.add_argument("--dry-run", action="store_true", help="print actions instead of doing them")
    ap.add_argument("--test-mic", action="store_true", help="test microphone levels and input")
    ap.add_argument("--list-mics", action="store_true", help="list microphones and exit")
    args = ap.parse_args()

    load_env(HERE / ".env")

    if args.list_mics:
        import sounddevice as sd
        print(sd.query_devices())
        return

    if args.test_mic:
        from audio import test_microphone
        mic = os.environ.get("MIC_DEVICE", "").strip()
        test_microphone(device=int(mic) if mic.isdigit() else (mic or None))
        return

    name = os.environ.get("ASSISTANT_NAME", "Jarvis")
    wake_words = [w.strip() for w in os.environ.get(
        "WAKE_WORDS", "hey jarvis,hi jarvis,ok jarvis,okay jarvis,jarvis").split(",") if w.strip()]
    names = (name.lower(),)

    dry_run = args.dry_run
    if sys.platform != "win32" and not dry_run:
        print(f"  [System] Running on {sys.platform}. System actions adapted for POSIX/Linux.")

    from llm import LLM
    llm = LLM(
        api_key=os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        model=os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite"),
        name=name,
    )
    apps = load_apps(HERE / "apps.json")

    # Select speaker
    if args.no_voice or args.text:
        from audio import ConsoleSpeaker
        speaker = ConsoleSpeaker(name)
    else:
        from audio import Speaker
        speaker = Speaker(name, os.environ.get("VOICE_HINT", ""))

    asst = Assistant(speaker, apps, llm, names, dry_run)

    # 1. Single text invocation
    if args.text:
        asst.handle(args.text)
        return

    # 2. Dynamic Island Widget mode
    if args.widget:
        from widget import DynamicIslandWidget
        w = DynamicIslandWidget(asst)
        w.root.mainloop()
        return

    # 3. Interactive text chat
    if args.chat:
        run_chat(asst)
        return

    # 4. Voice mode (wake-word or push-to-talk)
    try:
        run_voice(asst, wake_words, args.ptt, os.environ.get("PTT_KEY", "right ctrl"))
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
