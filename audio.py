"""Microphone capture, local Whisper transcription and speech output."""
from __future__ import annotations

import collections
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

SAMPLE_RATE = 16000
BLOCK = 512  # Optimal 32ms frame size for Silero Neural VAD
BLOCK_SECONDS = BLOCK / SAMPLE_RATE

# Whisper sometimes "hears" these in silence or background noise.
NOISE_PHRASES = {"you", "thank you", "thanks", "thanks for watching", "bye", "okay", "uh", "um", "hmm"}


# Global audio RMS meter level for real-time UI waveform visualizers
LATEST_AUDIO_LEVEL: float = 0.0


def _rms(x) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


class Listener:
    """Keeps the mic open and cuts the stream into spoken phrases using Silero Neural VAD."""

    def __init__(self, device=None, threshold: float | None = None):
        import sounddevice as sd
        self.q: queue.Queue = queue.Queue()
        env_th = os.environ.get("MIC_THRESHOLD", "").strip()
        self.manual_threshold = float(env_th) if env_th and env_th.replace(".", "", 1).isdigit() else threshold
        self.threshold = self.manual_threshold or 0.004

        # Silero VAD parameters
        vad_th_env = os.environ.get("VAD_THRESHOLD", "").strip()
        self.vad_threshold = float(vad_th_env) if vad_th_env and vad_th_env.replace(".", "", 1).isdigit() else 0.50

        vad_pause_env = os.environ.get("VAD_PAUSE_SECONDS", "").strip()
        self.vad_pause_seconds = float(vad_pause_env) if vad_pause_env and vad_pause_env.replace(".", "", 1).isdigit() else 0.35

        self.vad_model = None
        self.vad_available = False
        self._init_vad()

        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                     blocksize=BLOCK, device=device, callback=self._callback)

    def _init_vad(self):
        """Initialize Silero Neural VAD ONNX model for zero-false-positive speech gating."""
        try:
            from faster_whisper.vad import get_vad_model
            self.vad_model = get_vad_model()
            self.vad_available = True
            print("[Audio] Silero Neural VAD engine loaded successfully.")
        except Exception as e:
            self.vad_model = None
            self.vad_available = False
            print(f"[Audio] Silero VAD unavailable ({e}), using fallback RMS threshold.")

    def get_speech_prob(self, block: np.ndarray) -> float:
        """Calculate speech probability using Silero Neural VAD (0.0 = noise, 1.0 = human speech)."""
        if not self.vad_available or self.vad_model is None:
            rms = _rms(block)
            return min(1.0, max(0.0, rms / (self.threshold * 2)))
        try:
            if len(block) != 512:
                if len(block) < 512:
                    block = np.pad(block, (0, 512 - len(block)), mode="constant")
                else:
                    block = block[:512]
            prob = self.vad_model(block)
            return float(prob[0])
        except Exception:
            rms = _rms(block)
            return min(1.0, max(0.0, rms / (self.threshold * 2)))

    def _callback(self, indata, frames, time_info, status):
        global LATEST_AUDIO_LEVEL
        try:
            chunk = indata[:, 0].copy()
            LATEST_AUDIO_LEVEL = float(np.sqrt(np.mean(np.square(chunk)))) if len(chunk) else 0.0
            if hasattr(self, "q") and self.q is not None:
                self.q.put(chunk)
        except Exception:
            pass

    def start(self):
        try:
            if hasattr(self, "stream") and self.stream is not None and not self.stream.active:
                self.stream.start()
        except Exception:
            pass

    def stop(self):
        try:
            if hasattr(self, "stream") and self.stream is not None and self.stream.active:
                self.stream.stop()
        except Exception:
            pass

    def close(self):
        try:
            if hasattr(self, "stream") and self.stream is not None:
                if self.stream.active:
                    self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def flush(self):
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def calibrate(self, seconds: float = 0.5):
        self.flush()
        if self.vad_available:
            print(f"[Audio] Silero Neural VAD active (speech prob threshold: {self.vad_threshold:.2f}, dynamic silence cutoff: {int(self.vad_pause_seconds*1000)}ms)")
            return

        levels, end = [], time.time() + seconds
        while time.time() < end:
            try:
                levels.append(_rms(self.q.get(timeout=0.2)))
            except queue.Empty:
                pass
        noise_floor = float(np.median(levels)) if levels else 0.0001
        self.threshold = max(0.002, noise_floor * 3.5)
        print(f"Mic threshold: {self.threshold:.4f} (noise floor: {noise_floor:.5f})")

    def listen_phrase(self, start_timeout: float | None = None, max_seconds: float = 20.0):
        """Block until someone speaks a phrase using Silero Neural VAD. Returns float32 audio, or None."""
        pre = collections.deque(maxlen=int(0.35 / BLOCK_SECONDS))
        frames: list = []
        started, silence, consecutive_speech, t0 = False, 0, 0, time.time()

        while True:
            try:
                block = self.q.get(timeout=0.5)
            except queue.Empty:
                block = None

            if block is None:
                if not started and start_timeout and time.time() - t0 > start_timeout:
                    return None
                continue

            prob = self.get_speech_prob(block)
            is_speech = prob >= self.vad_threshold

            if not started:
                pre.append(block)
                if is_speech:
                    consecutive_speech += 1
                    # Require 2 consecutive frames (~64ms) or 1 strong frame (>0.70) to eliminate sharp clicks/snaps
                    if consecutive_speech >= 2 or prob >= 0.70:
                        started = True
                        frames = list(pre)
                        frames.append(block)
                        silence = 0
                else:
                    consecutive_speech = 0
                    if start_timeout and time.time() - t0 > start_timeout:
                        return None
            else:
                frames.append(block)
                silence = 0 if is_speech else silence + 1
                # Dynamic End-of-Speech: instantaneous cutoff when human speech pauses
                if silence * BLOCK_SECONDS >= self.vad_pause_seconds or len(frames) * BLOCK_SECONDS > max_seconds:
                    break

        if not frames:
            return None
        audio = np.concatenate(frames)
        return audio if len(audio) / SAMPLE_RATE >= 0.30 else None

    def record_phrase(self, start_timeout: float | None = 6.0, max_seconds: float = 20.0):
        """Alias for UI widgets / bridges."""
        return self.listen_phrase(start_timeout=start_timeout, max_seconds=max_seconds)

    def record_while(self, is_held):
        """Push-to-talk: record for as long as is_held() returns True."""
        self.flush()
        frames = []
        while is_held():
            try:
                frames.append(self.q.get(timeout=0.1))
            except queue.Empty:
                pass
        if not frames:
            return None
        audio = np.concatenate(frames)
        return audio if len(audio) / SAMPLE_RATE >= 0.3 else None


def test_microphone(device=None, duration: float = 6.0):
    """Diagnose microphone input levels with a live visual volume and Neural VAD meter."""
    import sounddevice as sd

    try:
        dev_info = sd.query_devices(device, "input")
        print(f"\n[Microphone Test] Using device: {dev_info.get('name', device)}")
    except Exception as e:
        print(f"\n[Microphone Test] Device error: {e}")
        return

    listener = Listener(device=device)
    print(f"Silero Neural VAD: {'ACTIVE' if listener.vad_available else 'INACTIVE'}")
    print("Speak or type on keyboard now... (testing for 6 seconds)\n")

    listener.start()
    t_end = time.time() + duration
    max_seen_rms = 0.0
    max_seen_vad = 0.0

    try:
        while time.time() < t_end:
            try:
                block = listener.q.get(timeout=0.2)
            except queue.Empty:
                continue
            rms = _rms(block)
            prob = listener.get_speech_prob(block)
            if rms > max_seen_rms:
                max_seen_rms = rms
            if prob > max_seen_vad:
                max_seen_vad = prob
            bars = int(min(rms / 0.02, 1.0) * 20)
            meter = "=" * bars + "-" * (20 - bars)
            status = " [SPEECH DETECTED]" if prob >= listener.vad_threshold else " [BACKGROUND / NOISE]"
            sys.stdout.write(f"\rLevel: [{meter}] RMS: {rms:.5f} | Neural VAD: {prob*100:4.1f}%{status}   ")
            sys.stdout.flush()
    finally:
        listener.close()

    print(f"\n\nMax RMS: {max_seen_rms:.5f} | Max Neural VAD: {max_seen_vad*100:.1f}%")
    if max_seen_vad >= 0.5:
        print("[OK] Silero Neural VAD successfully detected human speech!")
    elif max_seen_rms < 0.001:
        print("[!] Warning: Microphone level was very low. Check Windows mic mute, volume, or try another device index.")
    else:
        print("[OK] Microphone is picking up sound properly.")


class Transcriber:
    def __init__(self, model: str = "distil-small.en", device: str = "cpu", compute_type: str = "int8",
                 language: str | None = "en"):
        from faster_whisper import WhisperModel
        # Graceful fallback: try target model (distil-small.en, distil-medium.en, large-v3-turbo)
        # If offline or network error, fallback to cached base.en
        try:
            self.model = WhisperModel(model, device=device, compute_type=compute_type)
        except Exception as e:
            print(f"[Audio] Failed to load '{model}' ({e}), falling back to 'base.en'...")
            self.model = WhisperModel("base.en", device=device, compute_type=compute_type)
        self.language = language

    def __call__(self, audio) -> str:
        segments, _ = self.model.transcribe(
            audio, language=self.language, beam_size=1, vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt="Hey Jarvis. Open Chrome. Set a timer for five minutes. Turn the volume up.",
        )
        return " ".join(s.text.strip() for s in segments).strip()


class Speaker:
    """Text to speech through high-definition British neural voice (Jarvis).

    Uses Edge TTS (en-GB-RyanNeural) by default with authentic Paul Bettany
    British tone, and falls back to Windows SAPI (pyttsx3) if offline.
    """

    def __init__(self, name: str = "Jarvis", voice_hint: str = "", rate: int = 185):
        self.name = name
        self.voice_hint = voice_hint or os.environ.get("TTS_VOICE", "en-GB-RyanNeural")
        self.rate = rate
        self.after = None  # called after each utterance (used to flush the mic)
        self.q: queue.Queue = queue.Queue()
        self._current_alias: str | None = None
        self._stop_requested: bool = False
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        """Immediately stop speech playback and discard pending utterances (Barge-In)."""
        self._stop_requested = True
        alias = self._current_alias
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            try:
                winmm = ctypes.windll.winmm
                if alias:
                    winmm.mciSendStringW(f'stop {alias}', None, 0, 0)
                    winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                winmm.mciSendStringW('stop all', None, 0, 0)
                winmm.mciSendStringW('close all', None, 0, 0)
            except Exception:
                pass
        # Clear pending speech queue
        try:
            while True:
                _, done = self.q.get_nowait()
                done.set()
        except queue.Empty:
            pass

    def _play_mp3(self, path: str):
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            winmm = ctypes.windll.winmm
            alias = f"j_tts_{int(time.time()*1000)}"
            self._current_alias = alias
            self._stop_requested = False
            r_open = winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, 0)
            if r_open == 0:
                winmm.mciSendStringW(f'play {alias}', None, 0, 0)
                buf = ctypes.create_unicode_buffer(128)
                while not self._stop_requested:
                    winmm.mciSendStringW(f'status {alias} mode', buf, 128, 0)
                    if buf.value.lower() != "playing":
                        break
                    time.sleep(0.04)
                winmm.mciSendStringW(f'stop {alias}', None, 0, 0)
                winmm.mciSendStringW(f'close {alias}', None, 0, 0)
                self._current_alias = None
        else:
            # Linux / macOS audio playback
            for player in ["mpg123", "ffplay", "paplay", "pw-play", "aplay"]:
                if shutil.which(player):
                    cmd = [player]
                    if player == "ffplay":
                        cmd.extend(["-nodisp", "-autoexit", "-loglevel", "quiet"])
                    cmd.append(path)
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                if shutil.which(player):
                    cmd = [player]
                    if player == "ffplay":
                        cmd.extend(["-nodisp", "-autoexit", "-loglevel", "quiet"])
                    cmd.append(path)
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return

    def _speak_fish_audio(self, text: str) -> bool:
        """High-fidelity voice-cloned speech generation via Fish Audio API (Paul Bettany J.A.R.V.I.S.)."""
        api_key = os.environ.get("FISH_AUDIO_API_KEY", "").strip()
        voice_id = os.environ.get("FISH_AUDIO_VOICE_ID", "88b183bfbdda44a09ad4474712b967f4").strip()
        model = os.environ.get("FISH_AUDIO_MODEL", "s2.1-pro-free").strip()

        if not api_key:
            return False

        try:
            import urllib3
            urllib3.disable_warnings()
            import requests
            import tempfile
            from pathlib import Path

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if model:
                headers["model"] = model

            payload = {
                "text": text,
                "reference_id": voice_id,
                "format": "mp3"
            }

            r = requests.post("https://api.fish.audio/v1/tts", json=payload, headers=headers, verify=False, timeout=4.5)
            if r.status_code == 200 and len(r.content) > 1000:
                tmp_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                out_file = tmp_dir / f"fish_{int(time.time()*1000)}.mp3"
                out_file.write_bytes(r.content)

                self._play_mp3(str(out_file.resolve()))
                try:
                    out_file.unlink(missing_ok=True)
                except Exception:
                    pass
                return True
        except requests.exceptions.Timeout:
            print("  [fish audio server timed out -> switching to Edge-TTS instant fallback]")
        except Exception as e:
            print(f"  [fish audio error: {e}]")
        return False

    def _speak_neural(self, text: str) -> bool:
        try:
            import truststore
            truststore.inject_into_ssl()
        except Exception:
            pass

        try:
            import asyncio
            import edge_tts
            import tempfile
            from pathlib import Path

            voice = os.environ.get("TTS_VOICE", "en-GB-RyanNeural")
            rate = os.environ.get("TTS_RATE", "+0%")
            pitch = os.environ.get("TTS_PITCH", "-2Hz")

            tmp_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            out_file = tmp_dir / f"speech_{int(time.time()*1000)}.mp3"

            async def _gen():
                comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
                await comm.save(str(out_file))

            asyncio.run(_gen())

            if out_file.exists() and out_file.stat().st_size > 0:
                self._play_mp3(str(out_file.resolve()))
                try:
                    out_file.unlink(missing_ok=True)
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return False

    def _run(self):
        # Initialize COM on this worker thread for pyttsx3 fallback on Windows
        if sys.platform == "win32" and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

        sapi_engine = None
        try:
            import pyttsx3
            sapi_engine = pyttsx3.init()
            sapi_engine.setProperty("rate", self.rate)
            if self.voice_hint and "neural" not in self.voice_hint.lower():
                for v in sapi_engine.getProperty("voices"):
                    if self.voice_hint.lower() in v.name.lower():
                        sapi_engine.setProperty("voice", v.id)
                        break
        except Exception as e:
            print(f"[speech fallback disabled: {e}]")

        backend = os.environ.get("TTS_BACKEND", "").lower().strip()
        while True:
            text, done = self.q.get()
            print(f"{self.name}: {text}")

            spoken = False
            # 1. Try voice-cloned Fish Audio (authentic Paul Bettany) unless Edge-TTS is explicitly requested
            if backend not in ("edge_tts", "edge", "neural", "sapi"):
                spoken = self._speak_fish_audio(text)

            # 2. Try high-definition Edge-TTS (en-GB-RyanNeural) fallback
            if not spoken and backend != "sapi":
                spoken = self._speak_neural(text)

            # Fall back to offline SAPI5 if neural TTS failed
            if not spoken and sapi_engine:
                try:
                    sapi_engine.say(text)
                    sapi_engine.runAndWait()
                except Exception as e:
                    print(f"[speech error: {e}]")

            if self.after:
                self.after()
            done.set()

    def speak(self, text: str, wait: bool = True):
        if not text:
            return
        done = threading.Event()
        self.q.put((text, done))
        if wait:
            done.wait(60)


class ConsoleSpeaker:
    """Used for --text / --dry-run: just prints."""

    def __init__(self, name: str = "Jarvis"):
        self.name = name
        self.after = None

    def stop(self):
        pass

    def speak(self, text: str, wait: bool = True):
        if text:
            print(f"{self.name}: {text}")
