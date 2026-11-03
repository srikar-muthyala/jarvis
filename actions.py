"""Everything that touches Windows.

Each handler takes (arg, ctx) and returns the sentence to speak. With
ctx.dry_run set, nothing is executed; the action is printed instead, so you
can test the whole pipeline on any OS.
"""
from __future__ import annotations

import ctypes
import datetime
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.parse import quote_plus

from commands import fmt_duration, resolve_app

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB3
VK_LWIN, VK_D, VK_SNAPSHOT = 0x5B, 0x44, 0x2C
KEYEVENTF_KEYUP = 0x0002

# Never force-close these, even if someone puts them in apps.json.
PROTECTED_PROCESSES = {"explorer.exe", "svchost.exe", "csrss.exe", "winlogon.exe",
                       "services.exe", "lsass.exe", "dwm.exe", "wininit.exe", "smss.exe", "system"}

BROWSERS = {"chrome": "chrome", "google chrome": "chrome", "edge": "msedge",
            "microsoft edge": "msedge", "firefox": "firefox", "brave": "brave", "opera": "opera"}


def _pick(*options: str) -> str:
    return random.choice(options)


# --------------------------------------------------------------------------
# Low-level system & Windows helpers
# --------------------------------------------------------------------------

def _tap(vk: int, times: int = 1) -> None:
    if not IS_WINDOWS or not hasattr(ctypes, "windll"):
        return
    u = ctypes.windll.user32
    for _ in range(times):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _combo(modifier: int, vk: int) -> None:
    if not IS_WINDOWS or not hasattr(ctypes, "windll"):
        return
    u = ctypes.windll.user32
    u.keybd_event(modifier, 0, 0, 0)
    _tap(vk)
    u.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)


def _endpoint():
    """Master volume control via pycaw (handles old and new pycaw APIs)."""
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetSpeakers()
    if hasattr(dev, "EndpointVolume"):
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def _get_volume() -> int | None:
    if IS_WINDOWS:
        try:
            return round(_endpoint().GetMasterVolumeLevelScalar() * 100)
        except Exception:
            return None
    else:
        try:
            if shutil.which("pactl"):
                out = subprocess.check_output(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], text=True)
                m = re.search(r"(\d+)%", out)
                if m:
                    return int(m.group(1))
        except Exception:
            pass
        return None


def _set_volume(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    if IS_WINDOWS:
        try:
            _endpoint().SetMasterVolumeLevelScalar(percent / 100, None)
        except Exception:  # pycaw missing: fall back to volume keys (2% per press)
            _tap(VK_VOLUME_DOWN, 50)
            _tap(VK_VOLUME_UP, percent // 2)
    else:
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return percent


def _launch(target: str, *extra: str) -> None:
    if IS_WINDOWS:
        subprocess.Popen(["cmd", "/c", "start", "", target, *extra], creationflags=CREATE_NO_WINDOW)
    else:
        cmd = ["xdg-open", target] if shutil.which("xdg-open") else [target, *extra]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_menu_search(name: str) -> None:
    try:
        if IS_WINDOWS:
            subprocess.Popen(["cmd", "/c", "start", "", name], creationflags=CREATE_NO_WINDOW)
        else:
            cmd = ["xdg-open", name] if shutil.which("xdg-open") else [name]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"  [start search error: {e}]")


def _set_theme(mode: str) -> str:
    if not IS_WINDOWS or not hasattr(ctypes, "windll"):
        return mode
    import winreg
    path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        if mode == "toggle":
            light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
            mode = "dark" if light else "light"
        value = 1 if mode == "light" else 0
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 2, 5000, None)
    return mode


# --------------------------------------------------------------------------
# Context + timers
# --------------------------------------------------------------------------

class TimerManager:
    def __init__(self, notify):
        self.notify = notify
        self.items: dict[int, dict] = {}
        self.lock = threading.Lock()
        self.next_id = 1

    def add(self, seconds: int, label: str | None, reminder: bool) -> None:
        with self.lock:
            tid = self.next_id
            self.next_id += 1
            timer = threading.Timer(seconds, self._fire, args=(tid,))
            timer.daemon = True
            self.items[tid] = {"end": time.time() + seconds, "seconds": seconds,
                               "label": label, "reminder": reminder, "timer": timer}
            timer.start()

    def _fire(self, tid: int) -> None:
        with self.lock:
            item = self.items.pop(tid, None)
        if not item:
            return
        if item["reminder"]:
            self.notify(f"Reminder: {item['label']}.")
        elif item["label"]:
            self.notify(f"Your {item['label']} timer is done.")
        else:
            self.notify(f"Your {fmt_duration(item['seconds'])} timer is done.")

    def status(self) -> list[str]:
        with self.lock:
            return [f"{fmt_duration(max(0, i['end'] - time.time()))} left"
                    + (f" for {i['label']}" if i["label"] else "")
                    for i in sorted(self.items.values(), key=lambda i: i["end"])]

    def cancel_all(self) -> int:
        with self.lock:
            n = len(self.items)
            for i in self.items.values():
                i["timer"].cancel()
            self.items.clear()
        return n


class Context:
    def __init__(self, apps: dict, timers: TimerManager, dry_run: bool = False, names=("jarvis",), llm=None, speaker=None):
        self.apps, self.timers, self.dry_run, self.names = apps, timers, dry_run, names
        self.llm = llm
        self.speaker = speaker
        self.quit = False
        self.last_created_folder: Path | None = None
        self.last_query: str = ""
        self.widget = None

    def set_tool(self, name: str | None):
        if hasattr(self, "widget") and self.widget:
            try:
                self.widget.set_tool_badge(name)
            except Exception:
                pass

    def do(self, description: str, fn=None):
        if self.dry_run:
            print(f"    [dry-run] {description}")
            return True
        if not IS_WINDOWS:
            raise RuntimeError("This action only works on Windows.")
        return fn() if fn else True


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------

def h_open_app(name, ctx):
    name_str = str(name).strip()
    if name_str.lower().startswith("ms-settings:") or name_str.lower().startswith("shell:"):
        ctx.do(f"open {name_str}", lambda: _launch(name_str))
        return "Opening Windows Settings."
    hit = resolve_app(name, ctx.apps)
    if hit:
        key, entry = hit
        shown = entry.get("say") or key
        target = entry.get("launch")
        if target:
            ctx.do(f"launch {target}", lambda: _launch(target))
        else:
            ctx.do(f"search the Start menu for '{shown}'", lambda: _start_menu_search(shown))
        return _pick(f"Opening {shown}.", f"Okay, opening {shown}.", f"Sure, {shown}.")
    if len(name.split()) <= 3:
        ctx.do(f"search the Start menu for '{name}'", lambda: _start_menu_search(name))
        return f"I don't have {name} saved, so I'll look for it in the Start menu."
    return f"I don't know an app called {name}."


def h_close_app(name, ctx):
    hit = resolve_app(name, ctx.apps)
    if not hit:
        return f"I don't know an app called {name}. You can add it to apps dot json."
    key, entry = hit
    shown = entry.get("say") or key
    proc = entry.get("process")
    if not proc or proc.lower() in PROTECTED_PROCESSES:
        return f"I can't close {shown}."

    def run():
        r = subprocess.run(["taskkill", "/IM", proc], capture_output=True, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0

    ok = ctx.do(f"taskkill /IM {proc}", run)
    return _pick(f"Closed {shown}.", f"Okay, closing {shown}.") if ok else f"{shown} doesn't seem to be running."


def resolve_web_url(query_or_url: str) -> str:
    """If query_or_url is already a valid URL or domain, return it. Otherwise, search the web to locate the exact link."""
    raw = (query_or_url or "").strip()
    if not raw:
        return ""

    from urllib.parse import parse_qs, urlparse

    # If it is a search engine redirect/query URL (e.g. google.com/search?q=...), extract the real query
    if "google.com/search" in raw.lower() or "bing.com/search" in raw.lower() or "duckduckgo.com/?q=" in raw.lower():
        try:
            parsed = parse_qs(urlparse(raw).query)
            if "q" in parsed and parsed["q"][0]:
                raw = parsed["q"][0].strip()
        except Exception:
            pass
    elif re.match(r"^https?://", raw, re.IGNORECASE):
        return raw
    elif re.match(r"^[a-zA-Z0-9-]+\.(?:com|org|io|ai|net|dev|app|co|in|edu|gov)(?:/[^\s]*)?$", raw, re.IGNORECASE):
        return f"https://{raw}"

    # Search query resolution (e.g. 'genspark ai repo' or 'hyperframes github')
    try:
        import urllib3
        urllib3.disable_warnings()
        import requests

        search_q = raw
        if "repo" in raw.lower() and "github" not in raw.lower():
            search_q += " github"

        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": search_q},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            verify=False,
            timeout=6
        )
        if r.status_code == 200:
            candidates: list[str] = []
            for m in re.finditer(r'href=[\x22\x27]([^\x22\x27]+)[\x22\x27]', r.text):
                href = m.group(1)
                target = None
                if "duckduckgo.com/l/?uddg=" in href:
                    parsed = parse_qs(urlparse(href).query)
                    if "uddg" in parsed:
                        target = parsed["uddg"][0]
                elif href.startswith("http") and "duckduckgo" not in href:
                    target = href

                if target and not any(d in target.lower() for d in ("duckduckgo.com", "bing.com", "google.com", "yahoo.com")):
                    candidates.append(target)

            for c in candidates:
                if "github" in search_q.lower() and "github.com" in c.lower():
                    return c
            if candidates:
                return candidates[0]
    except Exception as e:
        print(f"  [resolve url error: {e}]")

    return f"https://www.google.com/search?q={quote_plus(raw)}"


def h_website(arg, ctx):
    site = arg["site"]
    url = resolve_web_url(site)
    browser = BROWSERS.get((arg.get("browser") or "").strip().lower())
    if browser:
        ctx.do(f"open {url} in {browser}", lambda: _launch(browser, url))
    else:
        ctx.do(f"open {url}", lambda: webbrowser.open(url))
    return f"Opening {url}."


def fetch_search_snippets(query: str, max_results: int = 5) -> list[str]:
    """Retrieve top real-time search result snippets from the web."""
    snippets: list[str] = []
    try:
        import urllib3
        urllib3.disable_warnings()
        import requests
        import html
        r = requests.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            verify=False,
            timeout=6
        )
        if r.status_code == 200:
            raw = re.findall(r"class='result-snippet'>(.*?)</td>", r.text, re.DOTALL)
            for s in raw:
                clean = html.unescape(re.sub(r"<.*?>", "", s)).strip()
                clean = re.sub(r"\s+", " ", clean)
                if clean and clean not in snippets:
                    snippets.append(clean)
                if len(snippets) >= max_results:
                    break
    except Exception as e:
        print(f"  [search snippets error: {e}]")
    return snippets


def h_web_search(query, ctx: Context) -> str:
    url = "https://www.google.com/search?q=" + quote_plus(query)
    ctx.do(f"open {url}", lambda: webbrowser.open(url))

    if ctx.dry_run:
        return f"[dry run] search: {query}"

    # Fetch live real-time snippets from the web
    snippets = fetch_search_snippets(query, max_results=5)
    if snippets:
        snippets_text = "\n".join(f"- {s}" for s in snippets)
        llm = getattr(ctx, "llm", None)
        if llm:
            try:
                prompt = (
                    f"The user asked: '{query}'.\n\n"
                    f"Live web search results:\n{snippets_text}\n\n"
                    f"Analyze these results and give a concise, accurate, direct answer to the user in 1 or 2 plain spoken sentences (no markdown or emojis). "
                    f"State the direct answer (such as current prices, values, or key facts) immediately."
                )
                answer = llm.ask(prompt)
                if answer and len(answer.strip()) > 8 and not answer.startswith("I can answer questions once you add an API key"):
                    return answer.strip()
            except Exception as e:
                print(f"  [llm search synthesis error: {e}]")

        # Fallback if LLM unavailable: return the cleanest top snippet
        clean_first = snippets[0]
        if len(clean_first) > 220:
            clean_first = clean_first[:217] + "..."
        return f"According to online search results: {clean_first}"

    return f"Searching Google for {query}."


def h_youtube(query, ctx):
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    ctx.do(f"open {url}", lambda: webbrowser.open(url))
    return f"Searching YouTube for {query}."


def h_volume_set(percent, ctx):
    ctx.do(f"set volume to {percent}%", lambda: _set_volume(percent))
    return f"Volume {percent} percent."


def h_volume_step(delta, ctx):
    def run():
        current = _get_volume()
        if current is None:  # no pycaw: each key press is about 2%
            _tap(VK_VOLUME_UP if delta > 0 else VK_VOLUME_DOWN, abs(delta) // 2)
            return None
        return _set_volume(current + delta)

    new = ctx.do(f"change volume by {delta:+d}%", run)
    if isinstance(new, int) and not isinstance(new, bool):
        return f"Volume {new} percent."
    return "Okay."


def h_mute(arg, ctx):
    want = 1 if arg == "mute" else 0

    def run():
        try:
            _endpoint().SetMute(want, None)
        except Exception:
            _tap(VK_VOLUME_MUTE)  # toggles

    ctx.do(arg, run)
    return "Muted." if want else "Unmuted."


def h_media(arg, ctx):
    vk = {"play_pause": VK_MEDIA_PLAY_PAUSE, "next": VK_MEDIA_NEXT, "previous": VK_MEDIA_PREV}[arg]
    ctx.do(f"media key: {arg}", lambda: _tap(vk))
    return {"play_pause": "Done.", "next": "Next track.", "previous": "Previous track."}[arg]


def h_lock(_, ctx):
    if IS_WINDOWS and hasattr(ctypes, "windll"):
        ctx.do("lock the PC", lambda: ctypes.windll.user32.LockWorkStation())
    else:
        ctx.do("lock the PC", lambda: subprocess.run(["loginctl", "lock-session"]) if shutil.which("loginctl") else subprocess.run(["xdg-screensaver", "lock"]))
    return "Locking."


def h_sleep(_, ctx):
    if IS_WINDOWS:
        cmd = (
            'Add-Type -Assembly System.Windows.Forms; '
            '[System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false)'
        )
        ctx.do("put the PC to sleep", lambda: subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", cmd],
            creationflags=CREATE_NO_WINDOW
        ))
    else:
        ctx.do("put the PC to sleep", lambda: subprocess.run(["systemctl", "suspend"]))
    return "Putting the computer to sleep."


def h_standby(_, ctx):
    if hasattr(ctx, "widget") and ctx.widget:
        try:
            ctx.widget._post_ui(lambda: ctx.widget.toggle_expand(False))
            ctx.widget.is_listening = False
        except Exception:
            pass
    return _pick("Standing by, sir.", "Going to sleep, sir. Call me if you need me.", "At ease, sir.")


def h_show_desktop(_, ctx):
    ctx.do("Win+D", lambda: _combo(VK_LWIN, VK_D))
    return "Showing the desktop."


def get_known_folder(name: str) -> Path:
    """Resolve true Windows folder paths (handles OneDrive redirection seamlessly)."""
    reg_names = {
        "desktop": "Desktop",
        "pictures": "My Pictures",
        "documents": "Personal",
        "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "music": "My Music",
        "videos": "My Video",
    }
    userprofile = Path(os.environ.get("USERPROFILE", "C:/Users/Default"))
    key_name = reg_names.get(name.lower().strip())
    if key_name and IS_WINDOWS:
        try:
            import winreg
            path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                val, _ = winreg.QueryValueEx(k, key_name)
                expanded = os.path.expandvars(str(val))
                return Path(expanded)
        except Exception:
            pass

    fallbacks = {
        "desktop": userprofile / "Desktop",
        "pictures": userprofile / "Pictures",
        "documents": userprofile / "Documents",
        "downloads": userprofile / "Downloads",
        "music": userprofile / "Music",
        "videos": userprofile / "Videos",
    }
    return fallbacks.get(name.lower().strip(), userprofile / name)


def get_screenshot_dir() -> Path:
    pref_file = Path(__file__).parent / "preferences.json"
    custom_dir = None
    if pref_file.exists():
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                custom_dir = data.get("screenshot_folder")
        except Exception:
            pass
    if custom_dir:
        clean = custom_dir.replace("\\", "/").strip().rstrip("/")
        if clean.lower().startswith("pictures/"):
            return get_known_folder("pictures") / clean[9:]
        p = Path(clean)
        return p if p.is_absolute() else get_known_folder("pictures") / p
    return get_known_folder("pictures") / "Jarvis"


def h_screenshot(_, ctx):
    target_dir = get_screenshot_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = target_dir / f"screenshot_{timestamp}.png"

    def capture():
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(filepath))
        except Exception as e:
            print(f"  [screenshot error: {e}]")
            _combo(VK_LWIN, VK_SNAPSHOT)

    ctx.do(f"save screenshot to {filepath}", capture)
    folder_name = target_dir.name
    parent_name = target_dir.parent.name
    return f"Screenshot saved to your {parent_name} {folder_name} folder."


def h_set_screenshot_folder(folder_path: str, ctx: Context) -> str:
    clean = folder_path.replace("\\", "/").strip().rstrip("/")
    if clean.lower().startswith("pictures/"):
        target = get_known_folder("pictures") / clean[9:]
        rel_str = f"Pictures/{clean[9:]}"
    elif clean.lower() in ("jarvis", "pictures/jarvis"):
        target = get_known_folder("pictures") / "Jarvis"
        rel_str = "Pictures/Jarvis"
    else:
        target = Path(os.environ.get("USERPROFILE", "C:/Users/Default")) / clean
        rel_str = clean

    target.mkdir(parents=True, exist_ok=True)
    pref_file = Path(__file__).parent / "preferences.json"
    prefs = {}
    if pref_file.exists():
        try:
            with open(pref_file, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except Exception:
            pass
    prefs["screenshot_folder"] = rel_str
    with open(pref_file, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)

    return f"I have created the {target.name} folder in {target.parent.name} and set it as your default screenshot location."


def parse_folder_request(target_str: str | None) -> tuple[str, str]:
    """Parse folder intent into (base_location, folder_name), e.g. ('desktop', 'test')."""
    if not target_str:
        return ("pictures", "Jarvis")
    t = target_str.lower().strip().rstrip("/")
    t = re.sub(r"\b(folder|directory|called|named|a|the|new)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t or t in ("there", "it", "it for me", "that", "that there", "you", "just created", "you just created"):
        return ("pictures", "Jarvis")
    if "/" in t or "\\" in t:
        parts = [p for p in re.split(r"[/\\]+", t) if p]
        if len(parts) >= 2:
            return (parts[0].lower(), parts[-1])
        elif len(parts) == 1:
            return ("pictures", parts[0])
    m = re.search(r"^(.*?)\s+(?:in|on)\s+([a-z]+)$", t)
    if m:
        return (m.group(2).strip().lower(), m.group(1).strip())
    m = re.search(r"^(?:in|on)\s+([a-z]+)\s+(.*?)$", t)
    if m:
        return (m.group(1).strip().lower(), m.group(2).strip())
    known_locs = ["desktop", "pictures", "documents", "downloads", "music", "videos"]
    for loc in known_locs:
        if loc in t:
            name = t.replace(loc, "").strip()
            return (loc, name or "Jarvis")
    return ("desktop", t)


def h_create_folder(arg: dict | str | None, ctx: Context) -> str:
    if isinstance(arg, str):
        folder_str = arg.strip()
    elif isinstance(arg, dict):
        folder_str = (arg.get("path_or_name") or arg.get("name") or arg.get("loc") or "").strip()
    else:
        folder_str = ""

    loc, name = parse_folder_request(folder_str)
    base_dir = get_known_folder(loc)
    target_path = base_dir / name

    try:
        target_path.mkdir(parents=True, exist_ok=True)
        ctx.last_created_folder = target_path
        loc_display = "Desktop" if loc.lower() == "desktop" else target_path.parent.name
        return f"Created folder {target_path.name} on your {loc_display}, sir."
    except Exception as e:
        print(f"  [create folder error: {e}]")
        return f"Failed to create folder {name} in {loc}."


def h_open_folder(arg: dict | str | None, ctx: Context) -> str:
    if isinstance(arg, str):
        fn = arg.lower().strip()
    elif isinstance(arg, dict):
        fn = (arg.get("folder_name") or arg.get("f") or arg.get("name") or "").lower().strip()
    else:
        fn = ""

    fn = re.sub(r"\b(folder|directory|named|called|the)\b", " ", fn).strip()

    # Contextual keywords referring to previous folder
    if not fn or fn in ("it", "that", "that folder", "you", "just created", "you just created"):
        if ctx.last_created_folder and ctx.last_created_folder.exists():
            target = ctx.last_created_folder
            ctx.do(f"open folder {target}", lambda: subprocess.Popen(["explorer.exe", str(target)]))
            return f"Opened the {target.name} folder."
        target = get_known_folder("desktop")
        ctx.do(f"open folder {target}", lambda: subprocess.Popen(["explorer.exe", str(target)]))
        return "Opened your Desktop."

    if fn in ("jarvis", "screenshots", "screenshot"):
        target = get_screenshot_dir()
    elif fn in ("desktop", "pictures", "documents", "downloads", "music", "videos"):
        target = get_known_folder(fn)
    else:
        if ctx.last_created_folder and ctx.last_created_folder.name.lower() == fn:
            target = ctx.last_created_folder
        else:
            found = None
            for base in ("desktop", "pictures", "documents", "downloads"):
                cand = get_known_folder(base) / fn
                if cand.exists():
                    found = cand
                    break
            if found:
                target = found
            elif ctx.last_created_folder:
                target = ctx.last_created_folder.parent / fn
            else:
                target = get_known_folder("desktop") / fn

    target.mkdir(parents=True, exist_ok=True)
    ctx.do(f"open folder {target}", lambda: subprocess.Popen(["explorer.exe", str(target)]))
    return f"Opened the {target.name} folder."


def h_theme(mode, ctx):
    result = ctx.do(f"theme: {mode}", lambda: _set_theme(mode))
    if mode == "toggle" and isinstance(result, str):
        mode = result
    return f"{mode.capitalize()} mode." if mode != "toggle" else "Done."


def h_timer(arg, ctx):
    secs, label, reminder = arg["seconds"], arg["label"], arg["reminder"]
    if ctx.dry_run:
        print(f"    [dry-run] timer for {secs}s label={label!r} reminder={reminder}")
    else:
        ctx.timers.add(secs, label, reminder)
    if reminder:
        return f"Okay, I'll remind you in {fmt_duration(secs)}."
    return f"Timer set for {fmt_duration(secs)}."


def h_timer_status(_, ctx):
    lines = ctx.timers.status()
    return " ".join(lines) + "." if lines else "You have no timers running."


def h_timer_cancel(_, ctx):
    n = ctx.timers.cancel_all()
    return "Cancelled." if n else "There were no timers to cancel."


def h_say_time(_, ctx):
    now = datetime.datetime.now()
    return f"It's {now.strftime('%I:%M %p').lstrip('0')}."


def h_say_date(_, ctx):
    now = datetime.datetime.now()
    return f"It's {now:%A}, {now:%B} {now.day}."


def h_system_stats(category, ctx):
    """Retrieve comprehensive real-time system telemetry (CPU, RAM, Disk, Battery)."""
    if ctx.dry_run:
        return "[dry run] system statistics check"
    try:
        import psutil
        cat = str(category or "all").lower().strip()

        # 1. CPU
        cpu_pct = int(round(psutil.cpu_percent(interval=0.15)))
        cpu_cores = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        ghz_str = f" at {cpu_freq.current / 1000:.1f} GHz" if cpu_freq and cpu_freq.current else ""

        # 2. RAM / Memory
        mem = psutil.virtual_memory()
        mem_pct = int(round(mem.percent))
        mem_used_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        mem_avail_gb = mem.available / (1024**3)

        # 3. Disk (Drive C)
        disk = psutil.disk_usage("C:/")
        disk_pct = int(round(disk.percent))
        disk_free_gb = disk.free / (1024**3)
        disk_total_gb = disk.total / (1024**3)

        # 4. Battery & Power
        bat = psutil.sensors_battery()
        bat_phrase = "connected to direct AC power"
        if bat is not None:
            b_pct = int(round(bat.percent))
            if bat.power_plugged:
                bat_phrase = f"battery is at {b_pct}% on AC power"
            else:
                secs = bat.secsleft
                if secs and secs > 0 and secs < 86400 * 3:
                    h = secs // 3600
                    m = (secs % 3600) // 60
                    bat_phrase = f"battery is at {b_pct}% with approximately {h}h {m}m remaining"
                else:
                    bat_phrase = f"battery is at {b_pct}% discharging"

        # Specific Subsystem Breakdowns
        if cat == "cpu":
            return f"CPU utilization is currently {cpu_pct}% across {cpu_cores} logical cores{ghz_str}, sir."
        elif cat in ("ram", "memory"):
            return f"Memory is at {mem_pct}% capacity, with {mem_used_gb:.1f} GB in use out of {mem_total_gb:.1f} GB ({mem_avail_gb:.1f} GB available)."
        elif cat in ("disk", "storage"):
            return f"Drive C is at {disk_pct}% capacity, with {disk_free_gb:.1f} GB free out of {disk_total_gb:.1f} GB."
        elif cat == "battery":
            return h_battery_status(None, ctx)

        # Full System Diagnostic Overview
        return (
            f"All systems nominal, sir. "
            f"CPU is at {cpu_pct}% across {cpu_cores} cores{ghz_str}, "
            f"RAM is at {mem_pct}% with {mem_used_gb:.1f} of {mem_total_gb:.1f} GB in use, "
            f"drive C has {disk_free_gb:.1f} GB available, and {bat_phrase}."
        )
    except Exception as e:
        print(f"  [system stats error: {e}]")
        return f"Unable to retrieve complete system diagnostics: {e}"


def h_battery_status(_, ctx):
    if ctx.dry_run:
        return "[dry run] battery status check"
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat is None:
            return "This system is running on direct AC power with no battery installed, sir."

        percent = int(round(bat.percent))
        plugged = bool(bat.power_plugged)
        secsleft = bat.secsleft

        # Check if secsleft is a valid positive duration
        has_time = secsleft not in (
            getattr(psutil, "POWER_TIME_UNLIMITED", -2),
            getattr(psutil, "POWER_TIME_UNKNOWN", -1),
            4294967295,
        ) and secsleft > 0 and secsleft < 86400 * 3

        if plugged:
            if percent >= 99:
                return f"We are fully charged at {percent}% and connected to AC power, sir."
            time_str = ""
            if has_time:
                h = secsleft // 3600
                m = (secsleft % 3600) // 60
                time_str = f" Approximately {h} hour{'s' if h != 1 else ''} and {m} minute{'s' if m != 1 else ''} until full charge."
            return f"The battery is currently at {percent}% and charging on AC power, sir.{time_str}"
        else:
            if has_time:
                h = secsleft // 3600
                m = (secsleft % 3600) // 60
                if h > 0:
                    dur_str = f"approximately {h} hour{'s' if h != 1 else ''} and {m} minute{'s' if m != 1 else ''}"
                else:
                    dur_str = f"approximately {m} minute{'s' if m != 1 else ''}"
                return f"We have {dur_str} of battery life remaining at {percent}%, sir."
            else:
                return f"We are currently running on battery at {percent}%, sir. Windows is currently calculating the remaining time based on our active system load."
    except Exception as e:
        print(f"  [battery status error: {e}]")
        return "I was unable to retrieve battery diagnostics at this time, sir."


def h_exit(_, ctx):
    ctx.quit = True
    return _pick("Goodbye.", "See you later.")


def h_stop(_, ctx):
    if hasattr(ctx, "speaker") and ctx.speaker:
        try:
            ctx.speaker.stop()
        except Exception:
            pass
    return ""


def resolve_youtube_video(query_or_channel: str, sort_by: str = "relevance") -> str:
    """Resolve a YouTube channel or search query to a direct watch URL with autoplay.

    sort_by: 'latest' (newest upload), 'views' (most viewed/popular), or 'relevance'.
    """
    import requests
    q = query_or_channel.strip()
    if sort_by == "latest":
        sp = "&sp=CAI%253D"
    elif sort_by in ("views", "most_viewed", "popular"):
        sp = "&sp=CAM%253D"
    else:
        sp = ""
    url = f"https://www.youtube.com/results?search_query={quote_plus(q)}{sp}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", r.text)
            if ids:
                return f"https://www.youtube.com/watch?v={ids[0]}&autoplay=1"
    except Exception as e:
        print(f"  [youtube resolver error: {e}]")
    return url


def h_play_youtube(arg: dict | str, ctx: Context) -> str:
    if isinstance(arg, str):
        arg = {"query_or_channel": arg}
    target = arg.get("query_or_channel", "").strip()
    sort_by = arg.get("sort_by", "")
    if not sort_by:
        if arg.get("latest"):
            sort_by = "latest"
        elif "most viewed" in target.lower() or "popular" in target.lower():
            sort_by = "views"
            target = re.sub(r"\b(most viewed|most popular|popular)\b", "", target, flags=re.IGNORECASE).strip()

    browser_hint = (arg.get("browser") or "").strip().lower()
    browser = BROWSERS.get(browser_hint)

    watch_url = resolve_youtube_video(target, sort_by=sort_by)
    if sort_by == "latest":
        label = f"the latest video from {target}"
    elif sort_by in ("views", "most_viewed", "popular"):
        label = f"the most viewed video from {target}"
    else:
        label = target

    if browser:
        ctx.do(f"play {label} on youtube in {browser}", lambda: _launch(browser, watch_url))
    else:
        ctx.do(f"play {label} on youtube", lambda: webbrowser.open(watch_url))

    b_str = f" in {browser_hint.title()}" if browser_hint else ""
    return f"Playing {label} on YouTube{b_str}."


def strip_html_tags(html: str) -> str:
    """Strip style, script, and HTML tags to extract clean readable text."""
    if not html:
        return ""
    import html as html_module
    cleaned = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<head[^>]*>[\s\S]*?</head>", " ", cleaned, flags=re.IGNORECASE)
    # Insert newlines for block-level elements so adjacent text doesn't merge
    cleaned = re.sub(r"<(?:p|div|h[1-6]|li|tr|br|hr|td)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    try:
        cleaned = html_module.unescape(cleaned)
    except Exception:
        pass
    cleaned = re.sub(r"&[a-zA-Z0-9#]+;", " ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    return " ".join(lines)


def decode_mime_words(raw_val: str) -> str:
    """Decode RFC 2047 MIME encoded headers like '=?UTF-8?B?...'."""
    if not raw_val:
        return ""
    try:
        from email.header import decode_header
        pieces = decode_header(raw_val)
        decoded = ""
        for piece, enc in pieces:
            if isinstance(piece, bytes):
                decoded += piece.decode(enc or "utf-8", errors="ignore")
            else:
                decoded += str(piece)
        return decoded.strip()
    except Exception:
        return str(raw_val).strip()


def clean_sender_name(raw_from: str) -> str:
    """Extract a clean, human-friendly sender name without raw email addresses or MIME encoding."""
    if not raw_from:
        return "Unknown Sender"
    decoded = decode_mime_words(raw_from)

    # If format is "Display Name <email@domain.com>", extract Display Name
    name = re.sub(r"<[^>]+>", "", decoded).strip().strip('"\'')

    # If name is empty or is itself an email address, extract a friendly company/person name
    if not name or "@" in name:
        m = re.search(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", decoded)
        if m:
            user_part, domain_full = m.group(1), m.group(2)
            domain_root = domain_full.split(".")[0]
            if domain_root.lower() in ("gmail", "yahoo", "outlook", "hotmail", "icloud"):
                name = user_part.replace(".", " ").replace("_", " ").title()
            else:
                name = domain_root.replace("-", " ").replace("_", " ").title()
        else:
            name = "Your Contact"

    # Clean any trailing punctuation or leftover MIME markers
    name = re.sub(r"=\?[^?]+\?[^?]+\?[^?]*\?=", "", name).strip()
    return name or "Your Contact"


def fetch_emails(query: str = "", count: int = 1, imap_server: str = "imap.gmail.com", user: str = "", password: str = "") -> list[dict]:
    """Fetch the latest N emails matching query via IMAP, ordered newest first."""
    import imaplib
    import email
    import re

    if not user or not password:
        return []

    count = max(1, min(10, count))

    try:
        mail = imaplib.IMAP4_SSL(imap_server, timeout=12)
        mail.login(user, password)
        mail.select("INBOX", readonly=True)

        if query:
            clean_q = re.sub(r'["\\]', "", query).strip()
            status, messages = mail.search(None, f'(OR SUBJECT "{clean_q}" BODY "{clean_q}")')
            if status != "OK" or not messages or not messages[0]:
                status, messages = mail.search(None, f'TEXT "{clean_q}"')
            if (status != "OK" or not messages or not messages[0]) and " " in clean_q:
                # If multi-word query produced no hits, search with the primary keywords
                for word in clean_q.split():
                    if len(word) >= 4 and word.lower() not in ("what", "status", "application", "email", "update", "updates", "emails", "inbox"):
                        status, messages = mail.search(None, f'(OR SUBJECT "{word}" BODY "{word}")')
                        if status == "OK" and messages and messages[0]:
                            break
        else:
            # Query Gmail primary category first to avoid promotional noise
            status, messages = mail.search(None, 'X-GM-RAW "category:primary"')
            if status != "OK" or not messages or not messages[0]:
                status, messages = mail.search(None, "ALL")

        if status != "OK" or not messages or not messages[0]:
            mail.logout()
            return []

        msg_ids = messages[0].split()
        if not msg_ids:
            mail.logout()
            return []

        # When listing top emails without a query, collect recent messages and prioritize distinct senders
        scan_count = max(count * 4, 15) if not query else count
        candidate_ids = list(reversed(msg_ids[-scan_count:]))
        results = []
        seen_senders = set()

        for mid in candidate_ids:
            if len(results) >= count:
                break

            status, data = mail.fetch(mid, "(RFC822)")
            if status != "OK" or not data:
                continue

            raw_email = None
            for item in data:
                if isinstance(item, tuple) and len(item) > 1:
                    raw_email = item[1]
                    break

            if not raw_email:
                continue

            msg = email.message_from_bytes(raw_email)

            subject = decode_mime_words(msg.get("Subject", "No Subject")) or "No Subject"
            sender_clean = clean_sender_name(msg.get("From", "Unknown Sender"))
            date_str = msg.get("Date", "")

            sender_key = sender_clean.lower().strip()
            if not query and sender_key in seen_senders:
                continue
            seen_senders.add(sender_key)

            plain_body = ""
            html_body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get("Content-Disposition") or "")
                    if "attachment" in cdispo:
                        continue
                    try:
                        payload = part.get_payload(decode=True)
                        if not payload:
                            continue
                        charset = part.get_content_charset() or "utf-8"
                        decoded = payload.decode(charset, errors="ignore").strip()
                        if ctype == "text/plain" and decoded:
                            if len(decoded) > len(plain_body):
                                plain_body = decoded
                        elif ctype == "text/html" and decoded:
                            cleaned_html = strip_html_tags(decoded)
                            if len(cleaned_html) > len(html_body):
                                html_body = cleaned_html
                    except Exception:
                        pass
            else:
                ctype = msg.get_content_type()
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        decoded = payload.decode(charset, errors="ignore")
                        if ctype == "text/html":
                            html_body = strip_html_tags(decoded)
                        else:
                            plain_body = decoded
                except Exception:
                    pass

            is_stub = bool(re.search(
                r"(?:cannot see the content|does not support the required display format|view (?:this )?email in (?:your )?browser|view as (?:a )?webpage|enable html|open in browser)",
                plain_body,
                re.IGNORECASE
            ))

            if (is_stub or len(html_body) > len(plain_body) * 1.2 or not plain_body) and html_body:
                body = html_body
            else:
                body = plain_body or html_body

            body = re.sub(r"\s+", " ", body).strip()[:3000]

            results.append({
                "subject": subject,
                "sender": sender_clean,
                "date": date_str,
                "body": body
            })

        mail.logout()
        return results
    except Exception as e:
        print(f"  [imap error] {e!r}")
        return []


def fetch_latest_email(query: str = "", imap_server: str = "imap.gmail.com", user: str = "", password: str = "") -> dict | None:
    """Fetch the latest email matching query via IMAP."""
    emails = fetch_emails(query=query, count=1, imap_server=imap_server, user=user, password=password)
    return emails[0] if emails else None


def h_summarize_email(arg: dict | str, ctx: Context) -> str:
    """Fetch and summarize the latest N emails matching query using Gemini."""
    import os
    if isinstance(arg, str):
        arg = {"query": arg}
    query = arg.get("query", "").strip()
    count = int(arg.get("count") or 1)

    # Detect count from query string if not explicitly given
    m_count = re.search(r"\b(?:top|latest|recent|last)?\s*(\d+)\s*(?:emails?|messages?)\b", query, re.IGNORECASE)
    if m_count:
        try:
            count = max(1, min(10, int(m_count.group(1))))
        except Exception:
            pass
        query = re.sub(r"\b(?:top|latest|recent|last)?\s*\d+\s*(?:emails?|messages?)\b", "", query, flags=re.IGNORECASE).strip()
    elif "top" in query.lower() or "recent" in query.lower() or "latest" in query.lower():
        if count == 1 and any(w in query.lower() for w in ("emails", "messages", "inbox")):
            count = 5

    # Clean generic phrases from query
    query = re.sub(r"\b(in my inbox|in inbox|from my inbox|inbox|emails?|messages?|summary|summarize)\b", "", query, flags=re.IGNORECASE).strip()

    user = os.environ.get("EMAIL_ADDRESS", "").strip()
    pwd = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    server = os.environ.get("EMAIL_IMAP_SERVER", "imap.gmail.com").strip()

    if not user or not pwd:
        # Fall back to opening search page on screen
        h_search_email({"query": query}, ctx)
        if query:
            return (
                f"I have opened your emails for '{query}' on screen. "
                "To have me read and summarize the contents aloud, configure your email in the dot env file."
            )
        return (
            "I have opened your Gmail inbox on screen. "
            "To have me read and summarize your emails aloud, configure your email in the dot env file."
        )

    ctx.do(f"fetch and summarize {count} email{'s' if count > 1 else ''} for {query}")
    emails = fetch_emails(query=query, count=count, imap_server=server, user=user, password=pwd)
    if not emails:
        if query:
            return f"I checked your inbox, but couldn't find any recent emails matching '{query}'."
        return "I checked your inbox, but couldn't find any recent emails."

    # 1. Single email summary
    if len(emails) == 1:
        em = emails[0]
        sender = em.get("sender", "Your Contact")
        subject = em.get("subject", "No Subject")

        try:
            import requests
            api_key = os.environ.get("LLM_API_KEY", "")
            model = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")
            if not api_key:
                snippet = re.sub(r"\s+", " ", em.get("body", "")).strip()[:140]
                snippet = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", snippet).strip()
                return f"From {sender}: '{subject}'. It states: {snippet}"

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            prompt = (
                "Summarize this email for the user in 2 to 3 concise natural spoken sentences without markdown, lists, or asterisks. "
                "Explain what the email is about and summarize its key news, topics, or message content. "
                "Never include or read raw email addresses, URLs, or technical delivery disclaimers.\n\n"
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Date: {em.get('date', '')}\n\n"
                f"Content:\n{em.get('body', '')}"
            )
            for attempt in range(2):
                r = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 200}},
                    timeout=14,
                )
                if r.status_code in (503, 429) and attempt < 1:
                    import time
                    time.sleep(1.0)
                    continue
                break
            if r.status_code == 200:
                summary = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                summary = re.sub(r"[*_#`]", "", summary)
                summary = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", summary)
                summary = re.sub(r"\s+", " ", summary).strip()
                if summary.lower().startswith("from ") or sender.lower() in summary.lower()[:len(sender) + 25]:
                    return summary
                return f"From {sender}. {summary}"
        except Exception as e:
            print(f"  [email summary error: {e}]")

        snippet = re.sub(r"\s+", " ", em.get("body", "")).strip()
        snippet = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", snippet).strip()
        if snippet:
            snippet = snippet[:150].rstrip() + ("..." if len(snippet) > 150 else "")
            return f"From {sender}, subject '{subject}'. It states: {snippet}"
        return f"You received an email from {sender} regarding '{subject}'."

    # 2. Multi-email summary (e.g. top 5 emails)
    email_blocks = []
    for idx, em in enumerate(emails, start=1):
        email_blocks.append(
            f"Email #{idx}:\n"
            f"From: {em['sender']}\n"
            f"Subject: {em['subject']}\n"
            f"Date: {em.get('date', '')}\n"
            f"Content: {em.get('body', '')[:600]}"
        )
    combined = "\n\n".join(email_blocks)

    try:
        import requests
        api_key = os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")
        if api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            prompt = (
                f"You are Jarvis. Summarize the following {len(emails)} recent emails for the user concisely in spoken form. "
                f"Provide a numbered list (1 to {len(emails)}) where each item states who it is from (use sender name, never raw email addresses) "
                "and a one-sentence summary of what it is about. Keep each item brief, direct, and conversational without markdown asterisks or technical headers.\n\n"
                f"{combined}"
            )
            for attempt in range(2):
                r = requests.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 350}},
                    timeout=16,
                )
                if r.status_code in (503, 429) and attempt < 1:
                    import time
                    time.sleep(1.0)
                    continue
                break
            if r.status_code == 200:
                summary = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                summary = re.sub(r"[*_#`]", "", summary)
                summary = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", summary)
                return summary.strip()
    except Exception as e:
        print(f"  [multi-email summary error: {e}]")

    items = []
    for idx, em in enumerate(emails, start=1):
        snip = re.sub(r"\s+", " ", em.get("body", "")).strip()[:90]
        items.append(f"{idx}. From {em['sender']}: '{em['subject']}'. {snip}")
    return f"Here is a summary of your latest {len(emails)} emails:\n" + "\n".join(items)


def h_search_email(arg: dict | str, ctx: Context) -> str:
    if isinstance(arg, str):
        arg = {"query": arg}
    query = arg.get("query", "").strip()
    provider = arg.get("provider", "gmail").lower()
    browser_hint = (arg.get("browser") or "").strip().lower()
    browser = BROWSERS.get(browser_hint)

    if "outlook" in provider:
        url = f"https://outlook.live.com/mail/0/search/id/?q={quote_plus(query)}" if query else "https://outlook.live.com/mail/0/inbox"
    else:
        url = f"https://mail.google.com/mail/u/0/#search/{quote_plus(query)}" if query else "https://mail.google.com/mail/u/0/#inbox"

    if browser:
        ctx.do(f"open email search for {query} in {browser}", lambda: _launch(browser, url))
    else:
        ctx.do(f"open email search for {query}", lambda: webbrowser.open(url))

    if query:
        return f"Searching your emails for {query}."
    return "Opening your email inbox."


def h_open_email_link(arg: dict | str, ctx: Context) -> str:
    """Find a URL in an email matching query and open it in the browser."""
    import os
    import re
    import webbrowser

    if isinstance(arg, str):
        arg = {"query": arg}
    raw_query = (arg.get("query") or "").strip()

    # Clean query for IMAP searching
    query = re.sub(
        r"\b(?:the|my|latest|recent|portal|website|web|links?|emails?|messages?|regarding|about|from|by|that|is|mentioned|given|provided|inside|in)\b",
        "",
        raw_query,
        flags=re.IGNORECASE
    ).strip()

    user = os.environ.get("EMAIL_ADDRESS", "").strip()
    pwd = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    server = os.environ.get("EMAIL_IMAP_SERVER", "imap.gmail.com").strip()

    if not user or not pwd:
        h_search_email({"query": query or "portal link"}, ctx)
        return "I have opened your Gmail search on screen so you can view the email links."

    ctx.do(f"searching email for links: {query or 'latest'}")
    emails = fetch_emails(query=query, count=5, imap_server=server, user=user, password=pwd)
    if not emails and query:
        emails = fetch_emails(query="", count=5, imap_server=server, user=user, password=pwd)

    if not emails:
        return f"I checked your emails, but couldn't find any messages{' regarding ' + raw_query if raw_query else ''}."

    junk_re = re.compile(
        r"(?:unsubscribe|optout|preferences|list-manage|tracking|pixel|clk\.|click\.|doubleclick|facebook\.com|twitter\.com|instagram\.com|linkedin\.com)",
        re.IGNORECASE
    )

    target_url = None
    target_email = None

    for em in emails:
        body = em.get("body", "")
        urls = re.findall(r"https?://[^\s<>\"')\]]+", body)
        cleaned_urls = []
        for u in urls:
            u_clean = u.rstrip(".,;!?:)'\"]")
            if not junk_re.search(u_clean):
                cleaned_urls.append(u_clean)

        if cleaned_urls:
            chosen = None
            if "portal" in raw_query.lower() or "support" in raw_query.lower():
                for u in cleaned_urls:
                    if "portal" in u.lower() or "support" in u.lower():
                        chosen = u
                        break
            if not chosen:
                chosen = cleaned_urls[0]

            target_url = chosen
            target_email = em
            break

    if not target_url:
        return f"I found the email from {emails[0].get('sender', 'the sender')}, but no direct link was found in the message."

    ctx.do(f"open {target_url}", lambda: webbrowser.open(target_url))
    sender = target_email.get("sender", "your email")
    return f"Opening {target_url} from your email by {sender}, sir."


def h_browse_page(arg: dict | str, ctx: Context) -> str:
    """Browse and read web page content using the Lightpanda headless browser."""
    import re
    from lightpanda_browser import fetch_url_markdown

    if isinstance(arg, str):
        arg = {"url": arg}
    raw_url = (arg.get("url") or "").strip()
    query = (arg.get("query") or "").strip()
    browser = (arg.get("browser") or "").strip()

    if not raw_url:
        return "Please specify a URL or topic for me to browse, sir."

    url = resolve_web_url(raw_url)

    # Open in browser if requested or if user command expressed open intent
    should_open = bool(browser or (isinstance(arg, dict) and arg.get("open")))
    if not should_open:
        raw_cmd = getattr(ctx, "last_query", "") or ""
        if re.search(r"\b(?:open|launch|visit|go to|show)\b", raw_cmd, re.IGNORECASE):
            should_open = True

    if should_open:
        b_target = BROWSERS.get(browser.lower()) if browser else None
        if b_target:
            ctx.do(f"open {url} in {b_target}", lambda: _launch(b_target, url))
        else:
            ctx.do(f"open {url}", lambda: webbrowser.open(url))

    ctx.do(f"browse {url} using Lightpanda")
    content = fetch_url_markdown(url, timeout_sec=12, max_chars=4000)
    if not content or content.startswith("Unable to retrieve"):
        return f"I had difficulty accessing {url}, sir."

    llm = getattr(ctx, "llm", None)
    if llm:
        try:
            if query:
                prompt = (
                    f"You browsed the web page at: {url}\n\n"
                    f"Page Content:\n{content}\n\n"
                    f"User question: {query}\n\n"
                    f"Answer the user's question directly and completely based on the page content in 2 to 3 natural spoken sentences without markdown or asterisks."
                )
            else:
                prompt = (
                    f"You browsed the web page at: {url}\n\n"
                    f"Page Content:\n{content}\n\n"
                    f"Explain what this project or repository is, what it does, and its key features for the user in 2 to 3 complete spoken sentences without markdown, lists, or asterisks."
                )
            answer = llm.ask(prompt)
            if answer and not answer.startswith("I can answer questions once you add an API key"):
                clean_ans = answer.strip()
                if not should_open:
                    clean_ans = f"{clean_ans.rstrip('.')} at {url}"
                return clean_ans
        except Exception as e:
            print(f"  [browse page llm error: {e}]")

    # Fallback if no LLM: return clean snippet of the page
    snippet = re.sub(r"\s+", " ", content).strip()
    if len(snippet) > 250:
        snippet = snippet[:247] + "..."
    return f"According to {url}: {snippet}"


def h_screen_vision(prompt: str, ctx: Context) -> str:
    """Analyze current screen visually using Gemini Multimodal Vision."""
    import os
    from vision import analyze_screen

    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "gemini-3.5-flash").strip()
    if not api_key:
        return "I need a Gemini API key configured to inspect your screen, sir."

    clean_prompt = (prompt or "").strip()
    ctx.do(f"inspect screen: {clean_prompt or 'visual analysis'}")
    return analyze_screen(clean_prompt, api_key, model)


def h_clipboard(arg: dict | str, ctx: Context) -> str:
    """Read, explain, translate, polish, or convert Windows clipboard content."""
    from clipboard_helper import process_clipboard

    if isinstance(arg, str):
        arg = {"action": arg}
    action_type = (arg.get("action") or "explain").strip()
    instruction = (arg.get("instruction") or "").strip()

    llm = getattr(ctx, "llm", None)
    ctx.do(f"process clipboard: {action_type}")
    spoken, _ = process_clipboard(action_type, instruction, llm)
    return spoken


def h_deep_research(topic: str, ctx: Context) -> str:
    """Execute deep multi-source web research with Lightpanda and save dossier."""
    from research_agent import deep_research_topic

    clean_topic = (topic or "").strip()
    if not clean_topic:
        return "Please specify a research topic, sir."

    spoken, _ = deep_research_topic(clean_topic, ctx)
    return spoken


def fetch_weather(city: str = "Coimbatore") -> str:
    """Fetch live weather for city via wttr.in with Open-Meteo fallback, including chance of rain."""
    import requests
    import urllib3
    import datetime
    urllib3.disable_warnings()

    city_clean = (city or "Coimbatore").strip()
    try:
        r = requests.get(f"https://wttr.in/{city_clean}?format=j1", timeout=6, verify=False)
        if r.status_code == 200:
            data = r.json()
            curr = data.get("current_condition", [{}])[0]
            cond = curr.get("weatherDesc", [{}])[0].get("value", "Clear")
            temp = curr.get("temp_C", "unknown")
            feels = curr.get("FeelsLikeC", temp)
            hum = curr.get("humidity", "unknown")

            # Extract chance of rain
            hourly = data.get("weather", [{}])[0].get("hourly", [])
            hour_idx = min(len(hourly) - 1, max(0, datetime.datetime.now().hour // 3)) if hourly else 0
            chance_rain = hourly[hour_idx].get("chanceofrain", "0") if hourly else "0"

            return (
                f"In {city_clean}, it is currently {cond} at {temp} degrees Celsius "
                f"(feels like {feels} degrees) with {hum} percent humidity "
                f"and a {chance_rain} percent chance of rain."
            )
    except Exception:
        pass

    try:
        lat, lon = 11.0168, 76.9558
        if city_clean.lower() != "coimbatore":
            geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city_clean}&count=1", timeout=5, verify=False).json()
            if "results" in geo and geo["results"]:
                lat = geo["results"][0]["latitude"]
                lon = geo["results"][0]["longitude"]
        om = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code&hourly=precipitation_probability",
            timeout=6,
            verify=False
        ).json()
        curr = om.get("current", {})
        t = round(curr.get("temperature_2m", 0))
        fl = round(curr.get("apparent_temperature", t))
        h = round(curr.get("relative_humidity_2m", 0))
        hourly_probs = om.get("hourly", {}).get("precipitation_probability", [])
        curr_hour = datetime.datetime.now().hour
        chance_rain = hourly_probs[curr_hour] if curr_hour < len(hourly_probs) else 0

        return (
            f"In {city_clean}, it is currently {t} degrees Celsius "
            f"(feels like {fl} degrees) with {h} percent humidity "
            f"and a {chance_rain} percent chance of rain."
        )
    except Exception:
        return f"Weather diagnostics for {city_clean} are currently unavailable."


_CAL_CACHE: dict = {"time": 0.0, "events": []}


def fetch_calendar_events() -> list[str] | None:
    """Fetch calendar events for today from Google Calendar iCal feed and Indian holidays.
    Always performs a live fetch without stale caching so newly added events are reflected immediately.
    Falls back to cached events only if the network request fails.
    Returns list of formatted events, empty list if clear, or None if unconfigured.
    """
    import os
    import re
    import datetime
    import time
    import requests
    import urllib3
    urllib3.disable_warnings()

    raw_urls = (os.environ.get("GOOGLE_CALENDAR_URL") or os.environ.get("CALENDAR_ICAL_URL") or os.environ.get("CALENDAR_URL") or "").strip()
    if not raw_urls:
        return None

    calendar_urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
    indian_holidays_url = "https://calendar.google.com/calendar/ical/en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics"
    if indian_holidays_url not in calendar_urls:
        calendar_urls.append(indian_holidays_url)

    today = datetime.date.today()
    today_str = today.strftime("%Y%m%d")
    today_day_code = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][today.weekday()]
    events = []
    seen = set()
    fetch_success = False

    for cal_url in calendar_urls:
        try:
            # Always bypass intermediate HTTP proxies and caches for fresh live data
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            r = requests.get(cal_url, headers=headers, timeout=10, verify=False)
            if r.status_code != 200:
                continue

            fetch_success = True
            for ev in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", r.text, re.DOTALL):
                m_sum = re.search(r"SUMMARY(?:;[^:]*)?:([^\r\n]+)", ev)
                if not m_sum:
                    continue
                summary = m_sum.group(1).strip()
                summary = summary.replace(r"\,", ",").replace(r"\;", ";").replace(r"\n", " ")
                if summary.lower() in seen:
                    continue

                m_dt = re.search(r"DTSTART(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", ev)
                if not m_dt:
                    continue
                ev_date = m_dt.group(1)
                hh, mm, ss, is_utc = m_dt.group(2), m_dt.group(3), m_dt.group(4), m_dt.group(5)

                m_end = re.search(r"DTEND(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", ev)
                end_date = m_end.group(1) if m_end else None

                is_today = False
                time_str = ""

                if hh and mm:
                    # Timed event: convert to local time if UTC
                    try:
                        start_dt = datetime.datetime(
                            int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]),
                            int(hh), int(mm), int(ss or 0)
                        )
                        if is_utc:
                            now_local = datetime.datetime.now()
                            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                            offset = now_local - now_utc
                            start_dt = start_dt + offset

                        if start_dt.date() == today:
                            is_today = True
                            h_int = start_dt.hour
                            m_int = start_dt.minute
                            period = "AM" if h_int < 12 else "PM"
                            display_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                            time_str = f" at {display_h}:{m_int:02d} {period}"
                        elif end_date:
                            end_hh = m_end.group(2) if m_end else None
                            end_mm = m_end.group(3) if m_end else None
                            end_ss = m_end.group(4) if m_end else None
                            end_utc = m_end.group(5) if m_end else None
                            if end_hh and end_mm:
                                end_dt = datetime.datetime(
                                    int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8]),
                                    int(end_hh), int(end_mm), int(end_ss or 0)
                                )
                                if end_utc:
                                    end_dt = end_dt + offset
                                if start_dt.date() < today <= end_dt.date():
                                    is_today = True
                    except Exception:
                        pass
                else:
                    # All-day event: DTEND is exclusive per RFC 5545
                    # (e.g. DTSTART: 20261029, DTEND: 20261030 is active ONLY on 2026-10-29)
                    try:
                        start_d = datetime.date(int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]))
                        if end_date:
                            end_d = datetime.date(int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8]))
                            if end_d > start_d:
                                is_today = (start_d <= today < end_d)
                            else:
                                is_today = (start_d == today)
                        else:
                            is_today = (start_d == today)
                    except Exception:
                        pass

                # Recurring events (RRULE)
                m_rrule = re.search(r"RRULE:([^\r\n]+)", ev)
                if not is_today and m_rrule:
                    rrule = m_rrule.group(1).upper()
                    m_until = re.search(r"UNTIL=(\d{8})", rrule)
                    if m_until and m_until.group(1) < today_str:
                        continue
                    try:
                        start_d = datetime.date(int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]))
                    except Exception:
                        continue
                    if start_d <= today:
                        m_count = re.search(r"COUNT=(\d+)", rrule)
                        cnt = int(m_count.group(1)) if m_count else None
                        if "FREQ=DAILY" in rrule:
                            if cnt is None or (today - start_d).days < cnt:
                                is_today = True
                        elif "FREQ=WEEKLY" in rrule:
                            if cnt is None or (today - start_d).days < cnt * 7:
                                if "BYDAY=" in rrule:
                                    days = rrule.split("BYDAY=")[1].split(";")[0].split(",")
                                    if today_day_code in days:
                                        is_today = True
                                elif start_d.weekday() == today.weekday():
                                    is_today = True
                        if is_today and hh and mm and not time_str:
                            try:
                                h_int, m_int = int(hh), int(mm)
                                if is_utc:
                                    now_local = datetime.datetime.now()
                                    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                    offset_min = int(round((now_local - now_utc).total_seconds() / 60))
                                    total_min = h_int * 60 + m_int + offset_min
                                    h_int = (total_min // 60) % 24
                                    m_int = total_min % 60
                                period = "AM" if h_int < 12 else "PM"
                                display_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                                time_str = f" at {display_h}:{m_int:02d} {period}"
                            except Exception:
                                pass

                if is_today:
                    # If the event is explicitly prefixed as a task, let fetch_tasks_today() handle it
                    if re.match(r"^(?:\[task\]|task\s*:|\[todo\]|todo\s*:)\s*", summary, re.IGNORECASE):
                        continue

                    seen.add(summary.lower())
                    if time_str:
                        events.append(f"{summary}{time_str}")
                    else:
                        events.append(f"{summary} (all day)")
        except Exception:
            pass

    if fetch_success:
        _CAL_CACHE["time"] = time.time()
        _CAL_CACHE["events"] = list(events)
        return events
    elif _CAL_CACHE.get("events") is not None:
        # Network failed; return fallback cached events if available
        return list(_CAL_CACHE["events"])
    return events


def h_weather(arg: dict | str, ctx: Context) -> str:
    """Report current weather for Coimbatore or requested city."""
    city = "Coimbatore"
    if isinstance(arg, str) and arg.strip():
        city = arg.strip()
    elif isinstance(arg, dict):
        city = arg.get("city") or arg.get("location") or "Coimbatore"
    ctx.do(f"fetch weather for {city}")
    return fetch_weather(city)


def normalize_title(text: str) -> str:
    """Normalize event or task title for robust duplicate detection."""
    import re
    t = re.sub(r"^(?:task\s*:|\[task\]|todo\s*:|\[todo\])\s*", "", text, flags=re.IGNORECASE)
    t = re.sub(r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\(all\s+day\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^\w\s]", "", t).strip().lower()
    return re.sub(r"\s+", " ", t)


def fetch_google_tasks_api() -> list[str]:
    """Fetch active tasks for today directly from Google Tasks API if token.json exists."""
    import os
    import json
    import re
    import datetime
    from pathlib import Path

    token_path = Path(__file__).resolve().parent / "token.json"
    if not token_path.exists():
        return []

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_data = json.loads(token_path.read_text(encoding="utf-8"))
        scopes = ["https://www.googleapis.com/auth/tasks.readonly"]
        creds = Credentials.from_authorized_user_info(token_data, scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")

        service = build("tasks", "v1", credentials=creds, cache_discovery=False)
        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")

        task_items = []
        lists_result = service.tasklists().list(maxResults=20).execute()
        for tlist in lists_result.get("items", []):
            list_id = tlist["id"]
            tasks_result = service.tasks().list(
                tasklist=list_id,
                showCompleted=False,
                showHidden=False,
                maxResults=100
            ).execute()

            for t in tasks_result.get("items", []):
                title = (t.get("title") or "").strip()
                if not title:
                    continue

                due_raw = t.get("due")
                time_str = ""
                is_today = False

                if due_raw:
                    m_due = re.match(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?", due_raw)
                    if m_due:
                        due_date_str = m_due.group(1)
                        due_h, due_m = m_due.group(2), m_due.group(3)
                        if due_h and due_m and (int(due_h) > 0 or int(due_m) > 0):
                            try:
                                utc_dt = datetime.datetime.strptime(due_raw[:19], "%Y-%m-%dT%H:%M:%S")
                                now_local = datetime.datetime.now()
                                now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                local_dt = utc_dt + (now_local - now_utc)
                                if local_dt.date() == today:
                                    is_today = True
                                    h_int, m_int = local_dt.hour, local_dt.minute
                                    period = "AM" if h_int < 12 else "PM"
                                    disp_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                                    time_str = f" at {disp_h}:{m_int:02d} {period}"
                            except Exception:
                                if due_date_str == today_str:
                                    is_today = True
                        else:
                            if due_date_str == today_str:
                                is_today = True
                else:
                    is_today = True

                if is_today:
                    notes = (t.get("notes") or "").strip()
                    if not time_str:
                        m_time = re.search(r"\b(?:at|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", f"{title} {notes}", re.IGNORECASE)
                        if m_time:
                            time_str = f" at {m_time.group(1).upper()}"

                    clean_title = re.sub(r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?.*$", "", title, flags=re.IGNORECASE).strip()
                    full_entry = f"{clean_title}{time_str}" if time_str else title
                    task_items.append(full_entry)

        return task_items
    except Exception as e:
        print(f"[GoogleTasks API] Note: {e}")
        return []


def h_calendar(arg: dict | str, ctx: Context) -> str:
    """Report today's scheduled calendar events and tasks."""
    ctx.do("fetch calendar events and tasks for today")
    events = fetch_calendar_events()
    tasks = fetch_tasks_today()

    # Deduplicate: if an event is also on the task list, avoid reading it twice
    if events and tasks:
        task_keys = {normalize_title(t) for t in tasks if normalize_title(t)}
        events = [ev for ev in events if normalize_title(ev) not in task_keys]

    parts = []
    if events:
        items = "; ".join(events)
        parts.append(f"{len(events)} calendar event{'s' if len(events) > 1 else ''}: {items}")

    if tasks:
        t_items = "; ".join(tasks)
        parts.append(f"{len(tasks)} task{'s' if len(tasks) > 1 else ''}: {t_items}")

    if parts:
        return f"On your schedule today, you have {'; and on your task list, you have '.join(parts)}."
    elif events is None and not tasks:
        return (
            "Your Google Calendar is not yet linked, sir. "
            "You can paste your Google Calendar secret iCal URL into the dot env file to sync your events, "
            "or say 'open google calendar' to view your agenda in your browser."
        )
    elif events is None and tasks:
        t_items = "; ".join(tasks)
        return f"Your calendar is not yet linked, but on your task list today, you have {len(tasks)} item{'s' if len(tasks) > 1 else ''}: {t_items}."
    return "Your calendar and task list are completely clear for today, sir. No scheduled events or pending tasks."


def fetch_tasks_today() -> list[str]:
    """Fetch active tasks for today from:
    1. tasks.json (local tasks)
    2. Google Calendar events explicitly marked as tasks (e.g. 'Task: ...' or '[Task] ...')
    3. GOOGLE_TASKS_URL (supports both VTODO and VEVENT feeds, e.g. dedicated Tasks calendars)
    """
    import os
    import json
    import re
    import datetime
    from pathlib import Path

    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    today_num = today.strftime("%Y%m%d")
    tasks = []
    seen = set()

    # 1. Local tasks from tasks.json
    tasks_file = Path(__file__).resolve().parent / "tasks.json"
    if tasks_file.exists():
        try:
            data = json.loads(tasks_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict) or item.get("completed"):
                        continue
                    task_date = str(item.get("date") or "").strip()
                    if not task_date or task_date == today_str:
                        title = item.get("title") or item.get("task") or "Untitled task"
                        time_str = str(item.get("time") or "").strip()
                        full_entry = f"{title} at {time_str}" if time_str else title
                        if full_entry.lower() not in seen:
                            seen.add(full_entry.lower())
                            tasks.append(full_entry)
        except Exception:
            pass

    # 2. Check Google Calendar events labeled as tasks (e.g. 'Task: ...', '[Task] ...')
    cal_urls_raw = (os.environ.get("GOOGLE_CALENDAR_URL") or os.environ.get("CALENDAR_ICAL_URL") or os.environ.get("CALENDAR_URL") or "").strip()
    if cal_urls_raw:
        try:
            import requests
            headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
            for u in [x.strip() for x in cal_urls_raw.split(",") if x.strip()]:
                r = requests.get(u, headers=headers, timeout=10, verify=False)
                if r.status_code != 200:
                    continue
                for ev in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", r.text, re.DOTALL):
                    m_sum = re.search(r"SUMMARY(?:;[^:]*)?:([^\r\n]+)", ev)
                    if not m_sum:
                        continue
                    raw_summary = m_sum.group(1).strip().replace(r"\,", ",").replace(r"\;", ";").replace(r"\n", " ")
                    m_task_match = re.match(r"^(?:\[task\]|task\s*:|\[todo\]|todo\s*:)\s*(?P<clean_title>.+)$", raw_summary, re.IGNORECASE)
                    if not m_task_match:
                        continue
                    clean_title = m_task_match.group("clean_title").strip()

                    # Check if today
                    m_dt = re.search(r"DTSTART(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", ev)
                    if not m_dt:
                        continue
                    ev_date = m_dt.group(1)
                    hh, mm, ss, is_utc = m_dt.group(2), m_dt.group(3), m_dt.group(4), m_dt.group(5)
                    m_end = re.search(r"DTEND(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", ev)
                    end_date = m_end.group(1) if m_end else None

                    is_today = False
                    time_str = ""
                    if hh and mm:
                        try:
                            start_dt = datetime.datetime(
                                int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]),
                                int(hh), int(mm), int(ss or 0)
                            )
                            if is_utc:
                                now_local = datetime.datetime.now()
                                now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                start_dt += (now_local - now_utc)
                            if start_dt.date() == today:
                                is_today = True
                                h_int, m_int = start_dt.hour, start_dt.minute
                                period = "AM" if h_int < 12 else "PM"
                                display_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                                time_str = f" at {display_h}:{m_int:02d} {period}"
                        except Exception:
                            pass
                    else:
                        try:
                            sd = datetime.date(int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]))
                            ed = datetime.date(int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8])) if end_date else sd
                            is_today = (sd <= today < ed) if ed > sd else (sd == today)
                        except Exception:
                            pass

                    if is_today:
                        full_entry = f"{clean_title}{time_str}"
                        if full_entry.lower() not in seen:
                            seen.add(full_entry.lower())
                            tasks.append(full_entry)
        except Exception:
            pass

    # 3. Dedicated Google Tasks / Tasks iCal URL (supports both VTODO and VEVENT)
    tasks_url = (os.environ.get("GOOGLE_TASKS_URL") or os.environ.get("TASKS_ICAL_URL") or "").strip()
    if tasks_url:
        try:
            import requests
            headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
            r = requests.get(tasks_url, headers=headers, timeout=10, verify=False)
            if r.status_code == 200:
                # 3a. Parse VTODO entries
                for todo in re.findall(r"BEGIN:VTODO(.*?)END:VTODO", r.text, re.DOTALL):
                    m_status = re.search(r"STATUS:([^\r\n]+)", todo)
                    if m_status and m_status.group(1).upper() in ("COMPLETED", "CANCELLED"):
                        continue
                    m_sum = re.search(r"SUMMARY(?:;[^:]*)?:([^\r\n]+)", todo)
                    if not m_sum:
                        continue
                    title = m_sum.group(1).strip().replace(r"\,", ",").replace(r"\;", ";")
                    m_due = re.search(r"(?:DUE|DTSTART)(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2}))?", todo)
                    if not m_due or m_due.group(1) == today_num:
                        hh, mm = (m_due.group(2), m_due.group(3)) if m_due else (None, None)
                        time_str = ""
                        if hh and mm:
                            h_int, m_int = int(hh), int(mm)
                            if "Z" in todo:
                                now = datetime.datetime.now()
                                utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                offset_min = int(round((now - utc_now).total_seconds() / 60))
                                total_min = h_int * 60 + m_int + offset_min
                                h_int = (total_min // 60) % 24
                                m_int = total_min % 60
                            period = "AM" if h_int < 12 else "PM"
                            display_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                            time_str = f" at {display_h}:{m_int:02d} {period}"
                        full_entry = f"{title}{time_str}"
                        if full_entry.lower() not in seen:
                            seen.add(full_entry.lower())
                            tasks.append(full_entry)

                # 3b. Parse VEVENT entries (if a secondary Google Calendar was linked as Tasks)
                for ev in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", r.text, re.DOTALL):
                    m_sum = re.search(r"SUMMARY(?:;[^:]*)?:([^\r\n]+)", ev)
                    if not m_sum:
                        continue
                    title = m_sum.group(1).strip().replace(r"\,", ",").replace(r"\;", ";").replace(r"\n", " ")
                    m_dt = re.search(r"DTSTART(?:;[^:]*)?:(\d{8})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", ev)
                    if not m_dt:
                        continue
                    ev_date = m_dt.group(1)
                    hh, mm = m_dt.group(2), m_dt.group(3)
                    m_end = re.search(r"DTEND(?:;[^:]*)?:(\d{8})", ev)
                    end_date = m_end.group(1) if m_end else None

                    is_today = False
                    time_str = ""
                    if hh and mm:
                        try:
                            start_dt = datetime.datetime(int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]), int(hh), int(mm))
                            if m_dt.group(5):
                                now_local = datetime.datetime.now()
                                now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                                start_dt += (now_local - now_utc)
                            if start_dt.date() == today:
                                is_today = True
                                h_int, m_int = start_dt.hour, start_dt.minute
                                period = "AM" if h_int < 12 else "PM"
                                display_h = h_int if (1 <= h_int <= 12) else (12 if h_int == 0 else h_int - 12)
                                time_str = f" at {display_h}:{m_int:02d} {period}"
                        except Exception:
                            pass
                    else:
                        try:
                            sd = datetime.date(int(ev_date[:4]), int(ev_date[4:6]), int(ev_date[6:8]))
                            ed = datetime.date(int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8])) if end_date else sd
                            is_today = (sd <= today < ed) if ed > sd else (sd == today)
                        except Exception:
                            pass

                    if is_today:
                        full_entry = f"{title}{time_str}"
                        if full_entry.lower() not in seen:
                            seen.add(full_entry.lower())
                            tasks.append(full_entry)
        except Exception:
            pass

    # 4. Google Tasks API (direct live sync if token.json is authenticated)
    try:
        for gt in fetch_google_tasks_api():
            norm = normalize_title(gt)
            if norm and norm not in seen:
                seen.add(norm)
                tasks.append(gt)
    except Exception:
        pass

    return tasks


def h_add_task(arg: dict | str, ctx: Context) -> str:
    """Add a new task to tasks.json."""
    import json
    import re
    import datetime
    from pathlib import Path

    title = ""
    time_str = ""
    if isinstance(arg, str):
        m = re.search(r"^(.*?)(?:\s+(?:at|by|for)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?$", arg.strip(), re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            time_str = m.group(2).strip() if m.group(2) else ""
        else:
            title = arg.strip()
    elif isinstance(arg, dict):
        title = (arg.get("title") or arg.get("task") or "").strip()
        time_str = (arg.get("time") or "").strip()

    title = re.sub(r"^(?:add\s+(?:a\s+)?task(?:\s+to)?|create\s+(?:a\s+)?task|task)\s+", "", title, flags=re.IGNORECASE).strip()

    if not title:
        return "What task would you like me to record, sir?"

    ctx.do(f"add task {title}")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    tasks_file = Path(__file__).resolve().parent / "tasks.json"

    data = []
    if tasks_file.exists():
        try:
            data = json.loads(tasks_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

    data.append({
        "title": title,
        "date": today_str,
        "time": time_str,
        "completed": False
    })
    tasks_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    time_part = f" at {time_str}" if time_str else ""
    return f"I have added '{title}{time_part}' to your tasks for today, sir."


def h_list_tasks(arg: dict | str, ctx: Context) -> str:
    """List active tasks for today."""
    ctx.do("list today's tasks")
    tasks = fetch_tasks_today()
    if tasks:
        items = "; ".join(tasks)
        return f"On your task list today, you have {len(tasks)} item{'s' if len(tasks) > 1 else ''}: {items}."
    return "Your task list is completely clear for today, sir."


def h_daily_digest(arg: dict | str, ctx: Context) -> str:
    """Synthesize full daily digest: Coimbatore weather, today's calendar, tasks, and latest 3 emails."""
    import os
    import re
    import datetime
    import requests

    ctx.do("compile daily digest")

    skip_greeting = False
    if isinstance(arg, dict) and arg.get("skip_greeting"):
        skip_greeting = True

    hour = datetime.datetime.now().hour
    if hour < 12:
        time_greeting = "Good morning, sir."
    elif hour < 17:
        time_greeting = "Good afternoon, sir."
    else:
        time_greeting = "Good evening, sir."

    greeting_prefix = "Certainly, sir. Here is your daily digest." if skip_greeting else f"{time_greeting} Here is your daily digest."

    # 1. Weather in Coimbatore
    weather_summary = fetch_weather("Coimbatore")

    # 2. Calendar and Tasks for today
    cal_events = fetch_calendar_events() or []
    tasks = fetch_tasks_today()

    # Deduplicate: if an event is also on your task list, announce it only once
    if cal_events and tasks:
        task_keys = {normalize_title(t) for t in tasks if normalize_title(t)}
        cal_events = [ev for ev in cal_events if normalize_title(ev) not in task_keys]

    sched_parts = []
    if cal_events:
        sched_parts.append(f"{len(cal_events)} calendar event{'s' if len(cal_events) > 1 else ''}: {'; '.join(cal_events)}")
    if tasks:
        sched_parts.append(f"{len(tasks)} task{'s' if len(tasks) > 1 else ''}: {'; '.join(tasks)}")

    if sched_parts:
        sched_summary = f"On your schedule today, you have {'; and on your task list, you have '.join(sched_parts)}."
    elif cal_events is None and not tasks:
        sched_summary = "Your Google Calendar and tasks are not yet linked."
    else:
        sched_summary = "Your calendar and task list are clear today, with no scheduled items."

    # 3. Latest 3 Emails
    user = os.environ.get("EMAIL_ADDRESS", "").strip()
    pwd = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    server = os.environ.get("EMAIL_IMAP_SERVER", "imap.gmail.com").strip()

    email_summary = ""
    if user and pwd:
        emails = fetch_emails(query="", count=3, imap_server=server, user=user, password=pwd)
        if emails:
            api_key = os.environ.get("LLM_API_KEY", "")
            model = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")
            if api_key:
                try:
                    blocks = []
                    for idx, em in enumerate(emails, 1):
                        safe_subj = em["subject"].encode("ascii", errors="replace").decode("ascii")
                        blocks.append(f"Email {idx}:\nFrom: {em['sender']}\nSubject: {safe_subj}\nContent: {em.get('body', '')[:350]}")
                    combined = "\n\n".join(blocks)

                    prompt = (
                        "Provide a smooth, natural spoken summary of these 3 latest emails. "
                        "For each email, state who it is from and a 1-sentence synopsis of the main update. "
                        "CRITICAL: Do NOT include any greeting (such as 'Good morning', 'Good afternoon', 'Hello'), salutation, intro pleasantries (such as 'I have processed your inbox' or 'here is your morning briefing'), or outro. "
                        "Start directly with the first email update (e.g. 'Starting with ...' or 'First, from ...'). "
                        "Do NOT use bullet points, asterisks, numbered lists, markdown, raw email addresses, or URLs. "
                        "Deliver as a continuous, elegant spoken narrative suitable for J.A.R.V.I.S.\n\n"
                        f"{combined}"
                    )
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 250}}, timeout=12)
                    if r.status_code == 200:
                        email_summary = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        email_summary = re.sub(r"[*_#`]", "", email_summary)
                except Exception:
                    pass

            if email_summary:
                # Strip out any greeting or intro fluff if LLM still included it
                email_summary = re.sub(
                    r"^(?:good\s+(?:morning|afternoon|evening)|hello|hi|greetings)[^.]*?\.\s*",
                    "",
                    email_summary,
                    flags=re.IGNORECASE,
                )
                email_summary = re.sub(
                    r"^(?:i\s+have\s+processed\s+your\s+inbox|here\s+is\s+your\s+(?:morning\s+|daily\s+)?briefing|here\s+are\s+your\s+updates)[^.]*?\.\s*",
                    "",
                    email_summary,
                    flags=re.IGNORECASE,
                )
                # Strip closing redundant pleasantries
                email_summary = re.sub(
                    r"\s*that\s+covers\s+your\s+(?:current\s+)?updates(?:\s+for\s+the\s+morning)?\.?\s*$",
                    "",
                    email_summary,
                    flags=re.IGNORECASE,
                ).strip()
            else:
                lines = []
                for em in emails:
                    lines.append(f"from {em['sender']} regarding '{em['subject']}'")
                email_summary = "In your inbox, you have recent messages " + "; and ".join(lines) + "."
        else:
            email_summary = "Your inbox currently has no new unread messages."
    else:
        email_summary = "Email monitoring is unconfigured in the environment file."

    digest = (
        f"{greeting_prefix} "
        f"{weather_summary} "
        f"{sched_summary} "
        f"Regarding your inbox: {email_summary}"
    )
    return re.sub(r"\s+", " ", digest).strip()


def execute_tool(tool_name: str, args: dict, ctx: Context) -> str:
    """Execute a tool called by the LLM agent loop."""
    if hasattr(ctx, "set_tool"):
        ctx.set_tool(tool_name)
    try:
        if tool_name == "open_app":
            app = args.get("app_name", "").strip()
            return h_open_app(app, ctx)

        elif tool_name == "close_app":
            app = args.get("app_name", "").strip()
            return h_close_app(app, ctx)

        elif tool_name == "open_website":
            url = args.get("url", "").strip()
            browser = args.get("browser", "").strip()
            return h_website({"site": url, "browser": browser}, ctx)

        elif tool_name == "play_youtube_video":
            return h_play_youtube(args, ctx)

        elif tool_name in ("search_email", "read_and_summarize_email"):
            # If asked to read/summarize, use h_summarize_email
            if tool_name == "read_and_summarize_email" or args.get("summarize"):
                return h_summarize_email(args, ctx)
            return h_search_email(args, ctx)

        elif tool_name == "open_email_link":
            return h_open_email_link(args, ctx)

        elif tool_name == "web_search":
            return h_web_search(args.get("query", ""), ctx)

        elif tool_name in ("browse_page", "browse_web_page", "read_web_page"):
            return h_browse_page(args, ctx)

        elif tool_name in ("screen_vision", "look_at_screen", "analyze_screen"):
            prompt = args.get("prompt") or args.get("query") or ""
            return h_screen_vision(prompt, ctx)

        elif tool_name in ("clipboard_action", "clipboard"):
            return h_clipboard(args, ctx)

        elif tool_name in ("deep_research", "research"):
            topic = args.get("topic") or args.get("query") or ""
            return h_deep_research(topic, ctx)

        elif tool_name == "control_volume":
            if "level" in args:
                return h_volume_set(int(args["level"]), ctx)
            elif "step" in args:
                return h_volume_step(int(args["step"]), ctx)
            elif "mute" in args:
                return h_mute("mute" if args["mute"] else "unmute", ctx)
            return "Volume unchanged."

        elif tool_name == "media_control":
            return h_media(args.get("action", "play_pause"), ctx)

        elif tool_name == "set_timer":
            secs = int(args.get("seconds", 60))
            label = args.get("label", "")
            return h_timer({"seconds": secs, "label": label, "reminder": bool(label)}, ctx)

        elif tool_name == "create_folder":
            return h_create_folder(args, ctx)

        elif tool_name == "open_folder":
            return h_open_folder(args, ctx)

        elif tool_name == "system_control":
            action = args.get("action", "")
            if action == "lock":
                return h_lock(None, ctx)
            elif action == "sleep":
                return h_sleep(None, ctx)
            elif action == "standby":
                return h_standby(None, ctx)
            elif action == "show_desktop":
                return h_show_desktop(None, ctx)
            elif action == "screenshot":
                return h_screenshot(None, ctx)
            elif action in ("dark_mode", "light_mode"):
                return h_theme("dark" if "dark" in action else "light", ctx)
            return "Unknown system action."

        elif tool_name == "get_time_date":
            t = h_say_time(None, ctx)
            d = h_say_date(None, ctx)
            return f"{t} {d}"

        elif tool_name in ("get_system_stats", "system_stats"):
            category = args.get("category", "all")
            return h_system_stats(category, ctx)

        elif tool_name in ("get_battery_status", "battery_status"):
            return h_battery_status(None, ctx)

        elif tool_name in ("daily_digest", "get_daily_digest"):
            return h_daily_digest(args, ctx)

        elif tool_name in ("weather", "get_weather"):
            city = args.get("city") or args.get("location") or "Coimbatore"
            return h_weather(city, ctx)

        elif tool_name in ("calendar", "get_calendar", "get_calendar_events"):
            return h_calendar(args, ctx)

        elif tool_name in ("add_task", "create_task"):
            return h_add_task(args, ctx)

        elif tool_name in ("list_tasks", "get_tasks"):
            return h_list_tasks(args, ctx)

        elif tool_name in ("stop", "silence", "stop_speaking"):
            return h_stop(None, ctx)

        elif tool_name in ("check_chat", "check_messages", "check_whatsapp"):
            app_target = args.get("app") or args.get("app_name") or "whatsapp"
            return h_check_chat(app_target, ctx)

        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        print(f"  [tool error] {tool_name}: {e!r}")
        return f"Failed to execute {tool_name}."
    finally:
        if hasattr(ctx, "set_tool"):
            ctx.set_tool(None)


def h_check_chat(app: str, ctx: Context) -> str:
    app_lower = (app or "whatsapp").lower().strip()
    shown = app_lower.title()
    if app_lower == "whatsapp":
        ctx.do("open WhatsApp", lambda: _launch("whatsapp:"))
    elif app_lower == "telegram":
        ctx.do("open Telegram", lambda: _launch("telegram:"))
    elif app_lower == "discord":
        ctx.do("open Discord", lambda: _launch("discord:"))
    elif app_lower == "slack":
        ctx.do("open Slack", lambda: _launch("slack:"))
    else:
        h_open_app(app_lower, ctx)
    return f"{shown} messages are end-to-end encrypted on your device and cannot be read in the background, sir. I have opened {shown} for you."


HANDLERS = {
    "open_app": h_open_app, "close_app": h_close_app, "website": h_website,
    "check_chat": h_check_chat,
    "web_search": h_web_search, "youtube": h_youtube, "play_youtube": h_play_youtube,
    "volume_set": h_volume_set, "volume_step": h_volume_step, "mute": h_mute, "media": h_media, "lock": h_lock,
    "sleep": h_sleep, "standby": h_standby, "show_desktop": h_show_desktop, "screenshot": h_screenshot,
    "theme": h_theme, "timer": h_timer, "timer_status": h_timer_status,
    "timer_cancel": h_timer_cancel, "say_time": h_say_time, "say_date": h_say_date,
    "battery_status": h_battery_status, "system_stats": h_system_stats,
    "email_summary": h_summarize_email, "email_search": h_search_email,
    "open_email_link": h_open_email_link,
    "browse_page": h_browse_page,
    "screen_vision": h_screen_vision,
    "clipboard": h_clipboard,
    "deep_research": h_deep_research,
    "daily_digest": h_daily_digest, "weather": h_weather, "calendar": h_calendar,
    "add_task": h_add_task, "list_tasks": h_list_tasks,
    "set_screenshot_dir": h_set_screenshot_folder, "create_folder": h_create_folder,
    "open_folder": h_open_folder,
    "stop": h_stop,
    "exit": h_exit,
}


def execute(action, ctx: Context) -> str:
    handler = HANDLERS.get(action.kind)
    if not handler:
        return "I can't do that yet."
    try:
        return handler(action.arg, ctx)
    except Exception as e:  # keep the assistant alive whatever happens
        print(f"  [error] {action.kind}: {e!r}")
        return "Sorry, that didn't work."
