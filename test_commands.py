"""Run with: python test_commands.py  (needs nothing installed)."""
from commands import Action, parse, resolve_app, load_apps, strip_wake

WAKE = ["hey jarvis", "hi jarvis", "okay jarvis", "jarvis"]


def kinds(text):
    return [(a.kind, a.arg) for a in parse(text)]


CASES = [
    ("open chrome", [("open_app", "chrome")]),
    ("Open Spotify.", [("open_app", "spotify")]),
    ("open the settings app", [("open_app", "settings")]),
    ("close chrome", [("close_app", "chrome")]),
    ("open youtube.com in brave", [("website", {"site": "youtube.com", "browser": "brave"})]),
    ("open youtube dot com", [("website", {"site": "youtube.com", "browser": None})]),
    ("volume up", [("volume_step", 10)]),
    ("turn it down", [("volume_step", -10)]),
    ("turn the volume down a little", [("volume_step", -5)]),
    ("make it louder", [("volume_step", 10)]),
    ("raise the volume by 15", [("volume_step", 15)]),
    ("set the volume to 40", [("volume_set", 40)]),
    ("set volume to fifty percent", [("volume_set", 50)]),
    ("max volume", [("volume_set", 100)]),
    ("mute", [("mute", "mute")]),
    ("unmute", [("mute", "unmute")]),
    ("pause the music", [("media", "play_pause")]),
    ("stop music", [("media", "play_pause")]),
    ("next song", [("media", "next")]),
    ("skip", [("media", "next")]),
    ("previous track", [("media", "previous")]),
    ("lock the computer", [("lock", None)]),
    ("go to sleep", [("standby", None)]),
    ("sleep jarvis", [("standby", None)]),
    ("standby", [("standby", None)]),
    ("put the computer to sleep", [("sleep", None)]),
    ("sleep the pc", [("sleep", None)]),
    ("dark mode", [("theme", "dark")]),
    ("take a screenshot", [("screenshot", None)]),
    ("what time is it", [("say_time", None)]),
    ("what's the date", [("say_date", None)]),
    ("system stats", [("system_stats", "all")]),
    ("how are the system stats", [("system_stats", "all")]),
    ("cpu usage", [("system_stats", "cpu")]),
    ("ram usage", [("system_stats", "ram")]),
    ("how much memory is free", [("system_stats", "ram")]),
    ("how long do you think our battery is going to last", [("battery_status", None)]),
    ("how much battery is left", [("battery_status", None)]),
    ("check battery", [("battery_status", None)]),
    ("cancel the timer", [("timer_cancel", None)]),
    ("stop the timer", [("timer_cancel", None)]),
    ("how long is left", [("timer_status", None)]),
    ("search for best pizza recipe", [("web_search", "best pizza recipe")]),
    ("search for salt and pepper", [("web_search", "salt and pepper")]),
    ("goodbye jarvis", [("exit", None)]),
    ("set a timer for 5 minutes", [("timer", {"seconds": 300, "label": None, "reminder": False})]),
    ("set a timer for five minutes", [("timer", {"seconds": 300, "label": None, "reminder": False})]),
    ("set a 10 minute timer", [("timer", {"seconds": 600, "label": None, "reminder": False})]),
    ("timer for 1 hour and 30 minutes", [("timer", {"seconds": 5400, "label": None, "reminder": False})]),
    ("set a timer for 5 minutes and 30 seconds", [("timer", {"seconds": 330, "label": None, "reminder": False})]),
    ("remind me in 20 minutes to call mum", [("timer", {"seconds": 1200, "label": "call mum", "reminder": True})]),
    ("remind me to drink water in 2 hours", [("timer", {"seconds": 7200, "label": "drink water", "reminder": True})]),
    ("pause spotify and open slack", [("media", "play_pause"), ("open_app", "slack")]),
    ("open notepad and calculator", [("open_app", "notepad"), ("open_app", "calculator")]),
    ("check my emails and let me know the status of my samyama application", [("email_summary", {"query": "samyama"})]),
    ("check for my latest emails regarding samyama", [("email_summary", {"query": "samyama"})]),
    ("check my email", [("email_summary", {"query": ""})]),
    ("status of my samyama application", [("email_summary", {"query": "samyama"})]),
    ("search my emails for flight tickets", [("email_search", {"query": "flight tickets"})]),
    ("from now on when i ask you to take a screenshot put that image in pictures/jarvis folder", [("set_screenshot_dir", "pictures/jarvis")]),
    ("create Pictures/Jarvis/", [("create_folder", "pictures/jarvis/")]),
    ("create Jarvis folder in Pictures", [("create_folder", "jarvis folder in pictures")]),
    ("first create that folder there", [("create_folder", "there")]),
    ("you do it for me", [("create_folder", None)]),
    ("create a folder named test in desktop", [("create_folder", "test in desktop")]),
    ("open it", [("open_folder", "it")]),
    ("open the folder named test you just created", [("open_folder", "test")]),
    ("open the test folder", [("open_folder", "test")]),
    ("open desktop", [("open_folder", "desktop")]),
    ("open pictures", [("open_folder", "pictures")]),
    ("open the jarvis folder", [("open_folder", "jarvis")]),
    ("open gmail", [("open_app", "gmail")]),
    ("gmail", [("open_app", "gmail")]),
    ("go to gmail", [("open_app", "gmail")]),
    ("check gmail", [("email_summary", {"query": ""})]),
    ("look for top 5 emails in my inbox and let me know the summary", [("email_summary", {"query": "", "count": 5})]),
    ("summarize the top 3 emails", [("email_summary", {"query": "", "count": 3})]),
    ("top 5 emails in my inbox", [("email_summary", {"query": "", "count": 5})]),
    ("daily digest", [("daily_digest", None)]),
    ("give me my daily digest", [("daily_digest", None)]),
    ("morning digest", [("daily_digest", None)]),
    ("brief me for today", [("daily_digest", None)]),
    ("start my day", [("daily_digest", None)]),
    ("start the day", [("daily_digest", None)]),
    ("what is the weather in coimbatore", [("weather", "coimbatore")]),
    ("weather in coimbatore", [("weather", "coimbatore")]),
    ("what's on my calendar today", [("calendar", None)]),
    ("check my calendar today", [("calendar", None)]),
    ("add task Night check-in at 8:45 PM", [("add_task", "night check-in at 8:45 pm")]),
    ("what are my tasks for today", [("list_tasks", None)]),
    ("check my tasks", [("list_tasks", None)]),
    ("open the portal link that is mentioned in the email by isha foundation regarding support portal", [("open_email_link", {"query": "isha foundation regarding support portal"})]),
    ("jarvis open the portal link that is mentioned in the email by isha foundation regarding support portal", [("open_email_link", {"query": "isha foundation regarding support portal"})]),
    ("can you open the portal link that is mentioned in the email by isha foundation regarding support portal", [("open_email_link", {"query": "isha foundation regarding support portal"})]),
    ("open the link in the email", [("open_email_link", {"query": ""})]),
    ("open the link mentioned in the email from isha foundation", [("open_email_link", {"query": "isha foundation"})]),
    ("open isha foundation email link", [("open_email_link", {"query": "isha foundation"})]),
    ("read the page https://example.com", [("browse_page", {"url": "https://example.com", "query": ""})]),
    ("browse https://example.com", [("browse_page", {"url": "https://example.com", "query": ""})]),
    ("summarize the page https://docs.wiz.io about pricing", [("browse_page", {"url": "https://docs.wiz.io", "query": "pricing"})]),
    ("stop", [("stop", None)]),
    ("shut up", [("stop", None)]),
    ("be quiet", [("stop", None)]),
    ("silence", [("stop", None)]),
    ("look at my screen", [("screen_vision", "")]),
    ("what is on my screen", [("screen_vision", "")]),
    ("look at my screen and tell me what error is showing", [("screen_vision", "what error is showing")]),
    ("explain my clipboard", [("clipboard", {"action": "explain", "instruction": ""})]),
    ("fix the grammar of my clipboard", [("clipboard", {"action": "grammar", "instruction": ""})]),
    ("translate my clipboard to French", [("clipboard", {"action": "translate", "instruction": "french"})]),
    ("deep research quantum computing breakthroughs", [("deep_research", "quantum computing breakthroughs")]),
    ("research the latest on solid state batteries", [("deep_research", "the latest on solid state batteries")]),
    # Not commands: these go to the question service.
    ("who wrote hamlet", []),
    ("what's the volume of a sphere", []),
    ("what's up with the sound of thunder", []),
]


def main():
    failures = 0
    for text, expected in CASES:
        got = kinds(text)
        if got != expected:
            failures += 1
            print(f"FAIL  {text!r}\n      expected {expected}\n      got      {got}")

    assert strip_wake("Hey Jarvis, open Spotify.", WAKE) == "open spotify"
    assert strip_wake("Jarvis", WAKE) == ""
    assert strip_wake("hey, jarvis", WAKE) == ""
    assert strip_wake("okay jarvis set a timer for 5 minutes", WAKE) == "set a timer for 5 minutes"
    assert strip_wake("hello there", WAKE) is None
    assert strip_wake("what is jarvis", WAKE) is None

    apps = {"vs code": {"launch": "code", "heard_as": ["vscode"]}, "chrome": "chrome", "spotify": {}}
    assert resolve_app("vscode", apps)[0] == "vs code"
    assert resolve_app("crome", apps)[0] == "chrome"
    assert resolve_app("spotifi", apps)[0] == "spotify"
    assert resolve_app("banana", apps) is None
    assert resolve_app("chrome", apps)[1] == {"launch": "chrome"}

    real = load_apps("apps.json")
    assert resolve_app("google chrome", real)[0] == "chrome"

    from actions import clean_sender_name, decode_mime_words, strip_html_tags
    assert clean_sender_name("=?UTF-8?B?SGluZHVzdGFuIFRpbWVz?=") == "Hindustan Times"
    assert clean_sender_name('"=?UTF-8?B?SGluZHVzdGFuIFRpbWVz?=" <newsletters@hindustantimes.com>') == "Hindustan Times"
    assert clean_sender_name("<support@swiggy.in>") == "Swiggy"
    assert clean_sender_name("john.doe@gmail.com") == "John Doe"
    assert decode_mime_words("=?UTF-8?B?SGluZHVzdGFuIFRpbWVz?=") == "Hindustan Times"
    assert "@" not in clean_sender_name("<alerts@hdfcbank.net>")
    html = "<p>Top news today:</p><ul><li>Story 1</li><li>Story 2</li></ul>"
    assert "Story 1" in strip_html_tags(html) and "Story 2" in strip_html_tags(html)

    if failures:
        raise SystemExit(f"{failures} case(s) failed")
    print(f"All {len(CASES)} parser cases and the wake-word/app checks passed.")


if __name__ == "__main__":
    main()
