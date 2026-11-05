"""Turn a spoken sentence into a list of actions.

Pure Python with no OS calls, so it can be tested anywhere (see test_commands.py).
Nothing here needs an LLM: commands are matched with plain patterns, which is
instant and free. Anything that isn't a command is treated as a question.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class Action:
    kind: str
    arg: Any = None


# --------------------------------------------------------------------------
# Text cleanup
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Lowercase, drop punctuation, turn 'youtube dot com' into 'youtube.com'."""
    t = text.lower().replace("’", "'").strip()
    t = re.sub(r"\s+dot\s+", ".", t)
    t = re.sub(r"[^\w\s.%:/'-]", " ", t)
    t = re.sub(r"(?<!\w)\.+|\.+(?!\w)", " ", t)  # sentence dots, keep "site.com"
    return re.sub(r"\s+", " ", t).strip()


def strip_wake(text: str, wake_words) -> str | None:
    """Return the command after the wake word, "" if only the wake word was
    said, or None if the sentence doesn't start with a wake word."""
    t = normalize(text)
    for w in sorted((normalize(x) for x in wake_words), key=len, reverse=True):
        if not w:
            continue
        if t == w:
            return ""
        if t.startswith(w + " "):
            return t[len(w) + 1:].strip()
    return None


# --------------------------------------------------------------------------
# Numbers and durations
# --------------------------------------------------------------------------

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_digits(t: str) -> str:
    tokens, out, i = t.split(), [], 0
    while i < len(tokens):
        w = tokens[i]
        if w in _TENS:
            val = _TENS[w]
            if i + 1 < len(tokens) and 1 <= _ONES.get(tokens[i + 1], 0) <= 9:
                val += _ONES[tokens[i + 1]]
                i += 1
            out.append(str(val))
        elif w in _ONES:
            out.append(str(_ONES[w]))
        else:
            out.append(w)
        i += 1
    return " ".join(out)


def _numeric(t: str) -> str:
    """Version of the text with number words as digits ("five" -> "5")."""
    t = re.sub(r"\b(?:one |a )?hundred\b", "100", t)
    t = words_to_digits(t)
    t = re.sub(r"\bhalf (?:an|a) hour\b", "30 minutes", t)
    t = re.sub(r"\bhalf (?:a|an) minute\b", "30 seconds", t)
    t = re.sub(r"\b(?:a|an) (hour|minute|second)\b", r"1 \1", t)
    return t


_UNIT_SECONDS = {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}
_DUR_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b")
_D = r"(?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\b(?:\s+and)?\s*)+"


def parse_duration(s: str) -> int | None:
    total, found = 0.0, False
    for num, unit in _DUR_PART.findall(s):
        total += float(num) * _UNIT_SECONDS[unit.rstrip("s")]
        found = True
    return int(round(total)) if found else None


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if sec or not parts:
        parts.append(f"{sec} second{'s' if sec != 1 else ''}")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Patterns
# --------------------------------------------------------------------------

_TV = r"(?:(?:set|start|create|make) )?"
RE_TIMER = re.compile(rf"^{_TV}(?:(?:a|an|the) )?timer (?:for |of )?(?P<d>{_D})(?:(?:called|named|for) (?P<l>.+))?$")
RE_TIMER2 = re.compile(rf"^{_TV}(?:(?:a|an|the) )?(?P<d>\d+(?:\.\d+)? ?-?(?:hour|hr|minute|min|second|sec)s?) timer(?: (?:called|named) (?P<l>.+))?$")
RE_REMIND1 = re.compile(rf"^remind me in (?P<d>{_D})to (?P<t>.+)$")
RE_REMIND2 = re.compile(rf"^remind me to (?P<t>.+?) in (?P<d>{_D})$")
RE_TIMER_CANCEL = re.compile(r"^(?:cancel|stop|delete|clear|remove|turn off) (?:all )?(?:the |my )?(?:timers?|reminders?|alarms?)$")
RE_TIMER_STATUS = re.compile(r"^(?:how (?:long|much time) (?:is )?(?:left|remaining)(?: on (?:the|my) timer)?|(?:what(?:'s| is) )?(?:the )?time (?:left|remaining)|check (?:the |my )?timers?|timer status|how long (?:left|remaining))$")

RE_MUTE = re.compile(r"^(?P<un>un)?mute(?: the)?(?: volume| sound| audio| computer| pc| laptop| speakers?)?$")
RE_VOL_SET = re.compile(r"^(?:(?:set|change|turn|put|make) )?(?:the )?(?:volume|sound)(?: level)? (?:to |at |on )?(?P<n>\d{1,3}) ?(?:%|percent)?$")
RE_VOL_MAX = re.compile(r"^(?:(?:set|turn|put) )?(?:the )?(?:volume (?:to )?(?:max|maximum|full)|(?:max|maximum|full) volume)$")

RE_PAUSE = re.compile(r"^(?:(?:pause|stop)(?: the)?(?: music| song| playback| track| video| it)?(?: on spotify)?|pause spotify)$")
RE_PLAY = re.compile(r"^(?:play|resume|unpause|continue)(?: the)?(?: music| song| playback| track| video| spotify| it)?$")
RE_NEXT = re.compile(r"^(?:(?:next|skip)(?: the| this| to the next)?(?: song| track| one)?|play (?:the )?next(?: song| track)?)$")
RE_PREV = re.compile(r"^(?:(?:previous|prev)(?: song| track| one)?|go back(?: a| one)?(?: song| track)?|play (?:the )?(?:previous|last) (?:song|track)|(?:the )?last (?:song|track))$")

RE_LOCK = re.compile(r"^lock(?: the| my)?(?: computer| pc| laptop| screen| system| windows)?$")
RE_PC_SLEEP = re.compile(
    r"^(?:"
    r"put (?:the |my )?(?:computer|pc|laptop|system|machine) to sleep|"
    r"sleep (?:the |my )?(?:computer|pc|laptop|system|machine)|"
    r"sleep mode|"
    r"(?:suspend|hibernate) (?:the |my )?(?:computer|pc|laptop|system|machine)"
    r")$"
)
RE_STANDBY = re.compile(
    r"^(?:"
    r"go to sleep|"
    r"sleep|"
    r"sleep (?:now|jarvis|assistant)|"
    r"standby|"
    r"stand by|"
    r"go on standby|"
    r"enter standby(?: mode)?|"
    r"(?:please )?(?:take a break|rest now|rest)|"
    r"(?:minimi[sz]e|hide|collapse)(?: (?:yourself|widget|hud|window))?"
    r")$"
)
RE_DESKTOP = re.compile(r"^(?:show (?:the )?desktop|minimi[sz]e (?:all|everything)(?: windows)?)$")
RE_SHOT = re.compile(r"^(?:take (?:a )?screenshot|screenshot|capture (?:the )?screen)$")
RE_THEME = re.compile(r"^(?:(?:turn on|switch to|enable|go|use) )?(?P<m>dark|light) (?:mode|theme)$")
RE_THEME_TOGGLE = re.compile(r"^(?:toggle|switch) (?:the )?(?:(?:dark|light) mode|theme)$")

RE_TIME = re.compile(r"^(?:what(?:'s| is) the time(?: now)?|what time is it(?: now)?|(?:tell me )?the time)$")
RE_DATE = re.compile(r"^(?:what(?:'s| is) (?:the )?(?:today's )?date(?: today)?|what day is it(?: today)?|what(?:'s| is) today(?:'s date)?)$")
RE_BATTERY = re.compile(
    r"^(?:"
    r"(?:how\s+(?:long|much\s+time)(?:\s+do\s+you\s+(?:think|estimate))?\s+(?:is\s+)?(?:our\s+|the\s+|my\s+)?battery(?:\s+is)?\s+(?:going\s+to\s+last|will\s+last|lasting)?)"
    r"|(?:how\s+long\s+(?:can|will)\s+(?:we|the\s+computer|this|the\s+laptop)\s+(?:run|last)\s+on\s+battery)"
    r"|(?:how\s+much\s+battery(?:\s+life)?(?:\s+(?:is|do\s+we\s+have))?\s*(?:left|remaining)?)"
    r"|(?:what(?:'s|\s+is)\s+(?:the\s+|our\s+|my\s+)?battery(?:\s+level|\s+percentage|\s+percent|\s+status|\s+life|\s+health)?)"
    r"|(?:check\s+(?:the\s+|our\s+|my\s+)?battery(?:\s+status|\s+level|\s+life)?)"
    r"|(?:battery\s+(?:status|level|percentage|life|info|check))"
    r"|(?:are\s+we\s+(?:charging|plugged\s+in|on\s+battery|on\s+ac(?:\s+power)?))"
    r"|(?:is\s+(?:the\s+|our\s+)?battery\s+(?:charging|plugged\s+in|low|dying|full))"
    r")$",
    re.IGNORECASE
)

RE_AUTOSTART = re.compile(
    r"^(?:"
    r"(?:(?:enable|turn\s+on|activate|start)\s+(?:auto\s*start|start\s+on\s+boot|boot\s+on\s+startup|startup|auto\s*boot))"
    r"|(?:(?:start|run|launch)\s+(?:on\s+boot|on\s+startup|when\s+(?:the\s+)?(?:pc|computer|system)\s+(?:boots|starts)))"
    r"|(?:(?:disable|turn\s+off|deactivate|stop)\s+(?:auto\s*start|start\s+on\s+boot|boot\s+on\s+startup|startup|auto\s*boot))"
    r"|(?:(?:don\'t|do\s+not)\s+(?:start|launch|boot|run)\s+(?:on\s+boot|on\s+startup|when\s+(?:the\s+)?(?:pc|computer|system)\s+(?:boots|starts)))"
    r"|(?:(?:is|check|status\s+of)\s+(?:auto\s*start|start\s+on\s+boot|startup))"
    r")$",
    re.IGNORECASE
)

RE_SYSTEM_STATS = re.compile(
    r"^(?:"
    r"(?:what\s+(?:are|is)\s+(?:the\s+|our\s+)?(?:system\s+)?(?:stats|status|diagnostics|telemetry|performance|health))"
    r"|(?:how\s+(?:are\s+the\s+system\s+stats|is\s+the\s+system(?:\s+(?:running|performing|doing))?))"
    r"|(?:(?:check|show|get|display|give\s+me)\s+(?:the\s+|our\s+)?(?:system\s+)?(?:stats|status|diagnostics|telemetry|performance|health|report))"
    r"|(?:system\s+(?:stats|status|diagnostics|telemetry|performance|health|info|report))"
    r"|(?:(?:stats|diagnostics|telemetry|performance)(?:\s+report)?)"
    r")$",
    re.IGNORECASE
)

RE_CPU_STATS = re.compile(
    r"^(?:"
    r"(?:what(?:\'s|\s+is)\s+(?:the\s+)?cpu(?:\s+(?:usage|utilization|load|percentage|status|stats))?)"
    r"|(?:how\s+is\s+(?:the\s+)?cpu(?:\s+doing)?)"
    r"|(?:(?:check|show|get)\s+(?:the\s+)?cpu(?:\s+(?:usage|utilization|load|stats))?)"
    r"|(?:cpu\s+(?:usage|utilization|load|percentage|status|stats|info))"
    r")$",
    re.IGNORECASE
)

RE_OPTIMIZE_MEMORY = re.compile(
    r"^(?:"
    r"(?:(?:clean|clear|free|optimize|flush|purge|reduce|lower)\s+(?:up\s+)?(?:the\s+|our\s+)?(?:system\s+)?(?:memory|ram|cache|memory\s+load|system\s+load|working\s+sets?))"
    r"|(?:(?:bring|get|lower|cut)\s+(?:the\s+)?(?:memory\s+|system\s+)?load\s+down)"
    r"|(?:optimize|free\s+up\s+ram|clean\s+ram|flush\s+ram|clear\s+ram|purge\s+ram|optimize\s+ram|clean\s+memory|free\s+memory|free\s+up\s+memory|optimize\s+memory)"
    r")$",
    re.IGNORECASE
)

RE_RAM_STATS = re.compile(
    r"^(?:"
    r"(?:what(?:\'s|\s+is)\s+(?:the\s+)?(?:ram|memory)(?:\s+(?:usage|utilization|status|stats))?)"
    r"|(?:how\s+much\s+(?:ram|memory)\s+(?:is\s+)?(?:used|in\s+use|free|available|left))"
    r"|(?:(?:check|show|get)\s+(?:the\s+)?(?:ram|memory)(?:\s+(?:usage|stats))?)"
    r"|(?:(?:ram|memory)\s+(?:usage|utilization|status|stats|info))"
    r")$",
    re.IGNORECASE
)

RE_DISK_STATS = re.compile(
    r"^(?:"
    r"(?:what(?:\'s|\s+is)\s+(?:the\s+)?(?:disk|storage|drive\s+c)(?:\s+(?:space|usage|status|stats))?)"
    r"|(?:how\s+much\s+(?:disk|storage|drive\s+c)\s+(?:space\s+)?(?:is\s+)?(?:left|free|available))"
    r"|(?:(?:check|show|get)\s+(?:the\s+)?(?:disk|storage|hard\s+drive)(?:\s+(?:space|usage|stats))?)"
    r"|(?:(?:disk|storage)\s+(?:space|usage|status|stats|info))"
    r")$",
    re.IGNORECASE
)

RE_DAILY_DIGEST = re.compile(
    r"^(?:"
    r"(?:(?:give\s+me\s+|tell\s+me\s+|what(?:'s|\s+is)\s+)?(?:the\s+|my\s+)?(?:daily\s+|morning\s+)?(?:digest|briefing|brief|summary|rundown|update))"
    r"|(?:brief\s+me(?:\s+for\s+today)?)"
    r"|(?:daily\s+digest|morning\s+digest|daily\s+briefing|morning\s+briefing)"
    r"|(?:(?:start|kick\s*off)\s+(?:the|my)\s+day)"
    r")$",
    re.IGNORECASE
)

RE_WEATHER = re.compile(
    r"^(?:"
    r"(?:(?:what(?:\'s|\s+is)\s+(?:the\s+)?weather(?:\s+(?:like|forecast))?|how(?:\'s|\s+is)\s+the\s+weather|weather\s+forecast|weather)(?:\s+(?:in|for|at)\s+(?P<city1>[\w\s.-]+?))?(?:\s+(?:today|now|outside))?)"
    r"|(?:is\s+it\s+(?:raining|sunny|cloudy|hot|cold)\s+(?:in\s+(?P<city2>[\w\s.-]+?)|outside))"
    r")$",
    re.IGNORECASE
)

RE_CALENDAR = re.compile(
    r"^(?:"
    r"(?:what(?:\'s|s|\s+is)\s+(?:on|in|there\s+on)\s+(?:the\s+|my\s+)?calenda?e?r(?:\s+(?:for|on)?\s*(?P<date1>today|tomorrow|yesterday|day\s+after\s+tomorrow|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:(?:check|show|get|list|display)\s+(?:the\s+|my\s+)?(?:calenda?e?r|agenda|schedule|meetings|events)(?:\s+(?:for|on)?\s*(?P<date2>today|tomorrow|yesterday|day\s+after\s+tomorrow|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:do\s+i\s+have\s+(?:any\s+)?(?:meetings|events|plans|schedule|calls)(?:\s+(?:for|on)?\s*(?P<date3>today|tomorrow|yesterday|day\s+after\s+tomorrow|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:what\s+do\s+i\s+have\s+(?:scheduled|planned|on)(?:\s+(?:for|on)?\s*(?P<date4>today|tomorrow|yesterday|day\s+after\s+tomorrow|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:(?:my\s+)?(?:schedule|agenda|calenda?e?r)(?:\s+(?:for|on)?\s*(?P<date5>today|tomorrow|yesterday|day\s+after\s+tomorrow|this\s+week|next\s+week|[\w\s.-]+))?)"
    r")$",
    re.IGNORECASE
)

RE_ADD_TASK = re.compile(
    r"^(?:(?:please\s+)?(?:add|create|record|note\s+down|put|set)(?:\s+(?:a|new))?\s+task(?:\s+(?:to|for|called|named))?\s+(?P<task>.+))$",
    re.IGNORECASE
)

RE_LIST_TASKS = re.compile(
    r"^(?:"
    r"(?:what\s+(?:are|is)\s+(?:the\s+|my\s+)?tasks?(?:\s+(?:for|on)?\s*(?P<date1>today|tomorrow|yesterday|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:(?:check|show|get|list|display|read)\s+(?:the\s+|my\s+)?tasks?(?:\s+(?:for|on)?\s*(?P<date2>today|tomorrow|yesterday|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:do\s+i\s+have\s+(?:any\s+)?tasks?(?:\s+(?:for|on)?\s*(?P<date3>today|tomorrow|yesterday|this\s+week|next\s+week|[\w\s.-]+))?)"
    r"|(?:(?:my\s+)?tasks?(?:\s+(?:for|on)?\s*(?P<date4>today|tomorrow|yesterday|this\s+week|next\s+week|[\w\s.-]+))?)"
    r")$",
    re.IGNORECASE
)

RE_SITE = re.compile(
    r"^(?:open|go to|launch|visit|load|take me to) (?:the )?(?:website )?"
    r"(?P<site>(?:https?://)?[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|ai|dev|app|co|in|edu|gov|tv|me|info|uk)(?:/\S*)?)"
    r"(?: (?:in|on|with|using) (?:the )?(?P<b>[a-z ]+?))?$"
)
RE_BROWSE_PAGE = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?)?"
    r"(?:browse|read|summarize|inspect|check\s+out|look\s+at)\s+"
    r"(?:(?:the\s+)?(?:page|website|site|url|article|link)\s+)?"
    r"(?P<url>(?:https?://)?[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|ai|dev|app|co|in|edu|gov|tv|me|info|uk)(?:/\S*)?)"
    r"(?:\s+(?:and\s+tell\s+me|for|about)\s+(?P<q>.+))?$",
    re.IGNORECASE
)
RE_STOP = re.compile(
    r"^(?:please\s+)?(?:stop|shut\s+up|be\s+quiet|quiet|silence|shh|pause|stop\s+speaking|cancel|halt)$",
    re.IGNORECASE
)
RE_SCREEN_VISION = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?)?"
    r"(?:look\s+at\s+(?:my\s+)?(?:screen|display)|inspect\s+(?:my\s+)?(?:screen|display)|what(?:'s|\s+is)\s+on\s+(?:my\s+)?(?:screen|display)|analyze\s+(?:my\s+)?(?:screen|display)|check\s+(?:my\s+)?(?:screen|display)|what\s+am\s+i\s+looking\s+at)"
    r"(?:\s+(?:and\s+tell\s+me|for|about)\s+(?P<q>.+))?$",
    re.IGNORECASE
)
RE_CLIPBOARD = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?)?"
    r"(?:"
      r"(?:explain|summarize|read|tell\s+me\s+about)\s+(?:my\s+clipboard|what\s+i\s+(?:just\s+)?copied)"
      r"|(?:fix|correct|polish|improve)\s+(?:the\s+)?(?:grammar\s+of\s+)?(?:my\s+clipboard|what\s+i\s+(?:just\s+)?copied)"
      r"|translate\s+(?:my\s+clipboard|what\s+i\s+(?:just\s+)?copied)(?:\s+to\s+(?P<lang>[a-zA-Z ]+))?"
      r"|convert\s+(?:my\s+clipboard|what\s+i\s+(?:just\s+)?copied)(?:\s+to\s+(?P<fmt>[a-zA-Z ]+))?"
    r")$",
    re.IGNORECASE
)
RE_RESEARCH = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?)?"
    r"(?:deep\s+research(?:\s+(?:on|into))?|deep\s+dive\s+(?:on|into)|do\s+(?:a\s+)?deep\s+dive\s+(?:on|into)|research|do\s+(?:some\s+)?research\s+(?:on|into))\s+"
    r"(?P<topic>.+)$",
    re.IGNORECASE
)
RE_YT = re.compile(r"^(?:(?:search|look up|find) youtube for (?P<q>.+)|search for (?P<q2>.+?) on youtube)$")
RE_YOUTUBE_URL_EXTRACT = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|v/)|youtu\.be/)([\w-]{11})[^\s]*",
    re.IGNORECASE
)
RE_CHAT_CHECK = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?)?"
    r"(?:(?:check|see|read|look\s+at|show\s+me|any|do\s+i\s+have\s+any)\s+)?"
    r"(?:if\s+i\s+have\s+any\s+)?(?:unread\s+|new\s+)?(?:messages?|chats?|texts?|notifications?)"
    r"\s+(?:on|in|from)\s+(?P<app>whatsapp|telegram|signal|slack|discord)$"
    r"|^(?:please\s+)?(?:check|open|show|read)\s+(?:my\s+)?(?P<app2>whatsapp|telegram|signal)\s*(?:messages?|chats?|unread)?$",
    re.IGNORECASE
)

RE_SEARCH = re.compile(r"^(?:google|(?:search|look up)(?: google| the web| online)?(?: for)?) (?P<q>.+)$")
RE_EMAIL_LINK = re.compile(
    r"^(?:please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|would\s+you\s+(?:please\s+)?)?"
    r"(?:open|launch|visit|go\s+to|click)\s+"
    r"(?:"
      r"(?:the\s+)?(?:portal\s+|website\s+|web\s+)?links?"
      r"(?:\s+(?:that\s+is\s+|which\s+is\s+)?(?:mentioned|given|provided|found|included|sent))?"
      r"(?:\s*(?:in|from|inside)\s+(?:the\s+|my\s+)?(?:latest\s+|recent\s+)?emails?"
      r"(?:\s+(?:from|by|about|regarding)\s+(?P<q1>.+))?)?"
    r"|"
      r"(?:the\s+)?(?P<q2>.+?)\s+emails?\s+(?:portal\s+|website\s+|web\s+)?links?"
    r")$",
    re.IGNORECASE
)
RE_EMAIL_SEARCH = re.compile(r"^(?:search|look up)(?: in)? (?:my )?(?:emails?|gmail|mail) (?:for|about) (?P<q>.+)$")
RE_EMAIL_ACTION = re.compile(
    r"^(?:"
    r"(?:please\s+)?(?:check|read|summarize|get|find|look\s+at|look|give\s+me(?:\s+a)?\s+summary\s+of)(?:\s+for)?\s+(?:the\s+|my\s+)?(?:latest\s+|recent\s+|last\s+|top\s+)?(?:\d+\s+)?(?:emails?|gmail|mail|messages?)"
    r"|(?:please\s+)?(?:check|summarize|read|look\s+at)\s+(?:my\s+)?(?:inbox|gmail|mail)"
    r"|(?:what(?:'s|\s+is)\s+|tell\s+me\s+)?(?:the\s+)?status\s+of\s+(?:my\s+)?.+?(?:\s+application)?"
    r"|(?:any\s+)?updates\s+(?:regarding|on|about)\s+(?:my\s+)?.+?"
    r"|(?:what\s+(?:are|is)\s+)?(?:the\s+|my\s+)?(?:top|latest|recent|last)\s+\d+\s+(?:emails?|messages?)"
    r"|(?:top|latest|recent|last)\s+\d+\s+(?:emails?|messages?)(?:\s+in\s+(?:my\s+)?inbox)?"
    r"|(?:look\s+for|search\s+for|find)\s+(?:the\s+|my\s+)?(?:top|latest|recent|last\s+)?(?:\d+\s+)?emails?"
    r")",
    re.IGNORECASE
)


def _extract_email_info(text: str) -> tuple[str, int]:
    t = text.lower().strip()
    count = 1
    m_num = re.search(r"\b(?:top|latest|recent|last)?\s*(\d+)\s*(?:emails?|messages?)\b", t)
    if m_num:
        try:
            count = max(1, min(10, int(m_num.group(1))))
        except Exception:
            count = 1

    q = ""
    m = re.search(r"\b(?:regarding|about|on|from)\s+(?:my\s+)?(.+?)(?:\s+application|\s+status|\s+update|\s+updates)?$", t)
    if m:
        q = m.group(1).strip()
        q = re.sub(r"\b(application|emails?|gmail|mail|inbox|the|my|latest|recent|top|\d+)\b", "", q).strip()
    if not q:
        m = re.search(r"(?:status of|updates (?:on|for))\s+(?:my\s+)?(.+?)(?:\s+application|\s+status)?$", t)
        if m:
            q = m.group(1).strip()
            q = re.sub(r"\b(application|emails?|gmail|mail|inbox|the|my|latest|recent|top|\d+)\b", "", q).strip()
    if not q:
        m = re.search(r"(?:emails?|gmail|mail|search|inbox)\s+(?:in\s+.*?\s+)?(?:for|about)\s+(?:my\s+)?(.+?)(?:\s+application)?$", t)
        if m:
            q = m.group(1).strip()
            q = re.sub(r"\b(application|emails?|gmail|mail|inbox|the|my|latest|recent|top|\d+)\b", "", q).strip()

    # Clean generic inbox / summary chatter from query
    q = re.sub(r"\b(top|\d+|emails?|inbox|summary|summarize|messages?|in\s+my\s+inbox|and\s+let\s+me\s+know|let\s+me\s+know)\b", "", q).strip()
    return q, count


def _extract_email_query(text: str) -> str:
    return _extract_email_info(text)[0]


RE_OPEN = re.compile(r"^(?:please )?(?:open|launch|start|switch to|bring up|fire up|go to|visit) (?:up )?(?:the )?(?P<app>[\w .+#&'-]+?)(?: (?:app|application|program))?$")
RE_CLOSE = re.compile(r"^(?:please )?(?:close|quit|exit|kill|terminate) (?:the )?(?P<app>[\w .+#&'-]+?)(?: (?:app|application|program|window))?$")

RE_SET_SCREENSHOT_DIR = re.compile(
    r"^(?:(?:from now on|in the future)[, ]+)?(?:(?:when i (?:ask you to )?take a screenshot|for screenshots?)[, ]+)?"
    r"(?:(?:put|save|store|keep)(?: that| the)? (?:images?|screenshots?) (?:in|to|inside) )"
    r"(?P<p>[\w/\\ .:-]+?)(?: folder| directory)?$"
)

RE_CREATE_FOLDER = re.compile(
    r"^(?:please\s+)?(?:first\s+)?(?:create|make|mkdir)\s+(?:(?:a|the|that)\s+)?(?:new\s+)?(?:folder|directory)?\s*(?:called|named)?\s*(?P<target>.+?)(?:\s+(?:folder|directory))?$"
    r"|^(?:you\s+)?(?:do\s+it|do\s+that|create\s+it|make\s+it)(?:\s+for\s+me)?$"
)

RE_OPEN_FOLDER = re.compile(
    r"^(?:please\s+)?open\s+(?:the\s+)?(?:folder\s+(?:called\s+|named\s+)?(?P<f1>[\w -]+?)(?:\s+(?:you\s+)?(?:just\s+)?created)?|(?P<f2>[\w -]+?)\s+(?:folder|directory)(?:\s+(?:you\s+)?(?:just\s+)?created)?)$"
    r"|^(?:please\s+)?open\s+(?P<it>it|that|that\s+folder|the\s+folder(?:\s+you\s+just\s+created)?)$"
    r"|^(?:please\s+)?open\s+(?:the\s+)?(?P<f3>pictures|screenshots|jarvis|downloads|documents|desktop|music|videos)(?:\s+(?:folder|directory))?$"
)

_SPLIT = re.compile(r"\s+(?:and then|and also|and|then|also)\s+")
_NO_SPLIT = {
    "timer", "web_search", "youtube", "email_summary", "email_search", "open_email_link", "browse_page",
    "screen_vision", "clipboard", "deep_research", "stop", "check_chat", "youtube_summary",
    "set_screenshot_dir", "create_folder", "open_folder", "battery_status",
    "system_stats", "optimize_memory", "autostart", "daily_digest", "weather", "calendar", "add_task", "list_tasks"
}

_UP = {"up", "raise", "increase", "louder", "higher", "pump", "crank"}
_DOWN = {"down", "lower", "decrease", "reduce", "quieter", "softer"}
_VOL_STARTS = {"turn", "make", "bring", "pump", "crank", "raise", "increase", "lower",
               "decrease", "reduce", "volume", "louder", "quieter", "softer", "a", "it"}
_SOUNDISH = {"volume", "sound", "music", "it", "louder", "quieter", "softer"}


def _volume_step(t: str, td: str) -> Action | None:
    words = t.split()
    if not words or len(words) > 9 or words[0] not in _VOL_STARTS:
        return None
    ws = set(words)
    up, down = bool(ws & _UP), bool(ws & _DOWN)
    if up == down or not (ws & _SOUNDISH):
        return None
    m = re.search(r"\bby (\d+)", td)
    if m:
        amount = int(m.group(1))
    elif "lot" in ws:
        amount = 20
    elif ws & {"bit", "little"}:
        amount = 5
    else:
        amount = 10
    return Action("volume_step", amount if up else -amount)


def _parse_single(t: str, names) -> Action | None:
    td = _numeric(t)
    alt = "|".join(re.escape(normalize(n)) for n in names) or "jarvis"
    if re.match(rf"^(?:goodbye|bye|bye bye|exit|quit)(?: (?:{alt}|assistant))?$"
                rf"|^(?:quit|exit|stop|close|shut down) (?:{alt}|assistant|yourself)$", t):
        return Action("exit")
    if re.match(rf"^(?:go to sleep|sleep|standby)(?: (?:{alt}|assistant))?$", t):
        return Action("standby")
    if RE_STOP.match(t):
        return Action("stop")

    if RE_TIMER_CANCEL.match(t):
        return Action("timer_cancel")
    if RE_TIMER_STATUS.match(t):
        return Action("timer_status")

    for rx in (RE_TIMER, RE_TIMER2):
        m = rx.match(td)
        if m:
            secs = parse_duration(m.group("d"))
            if secs:
                return Action("timer", {"seconds": secs, "label": m.group("l"), "reminder": False})
    for rx in (RE_REMIND1, RE_REMIND2):
        m = rx.match(td)
        if m:
            secs = parse_duration(m.group("d"))
            if secs:
                return Action("timer", {"seconds": secs, "label": m.group("t"), "reminder": True})

    m = RE_MUTE.match(t)
    if m:
        return Action("mute", "unmute" if m.group("un") else "mute")
    m = RE_VOL_SET.match(td)
    if m:
        return Action("volume_set", min(100, int(m.group("n"))))
    if RE_VOL_MAX.match(t):
        return Action("volume_set", 100)

    if RE_PAUSE.match(t) or RE_PLAY.match(t):
        return Action("media", "play_pause")
    if RE_NEXT.match(t):
        return Action("media", "next")
    if RE_PREV.match(t):
        return Action("media", "previous")

    a = _volume_step(t, td)
    if a:
        return a

    if RE_LOCK.match(t):
        return Action("lock")
    if RE_PC_SLEEP.match(t):
        return Action("sleep")
    if RE_STANDBY.match(t):
        return Action("standby")
    if RE_DESKTOP.match(t):
        return Action("show_desktop")
    if RE_SHOT.match(t):
        return Action("screenshot")
    m = RE_THEME.match(t)
    if m:
        return Action("theme", m.group("m"))
    if RE_THEME_TOGGLE.match(t):
        return Action("theme", "toggle")

    if RE_TIME.match(t):
        return Action("say_time")
    if RE_DATE.match(t):
        return Action("say_date")
    if RE_SYSTEM_STATS.match(t):
        return Action("system_stats", "all")
    if RE_CPU_STATS.match(t):
        return Action("system_stats", "cpu")
    if RE_AUTOSTART.match(t):
        t_low = t.lower()
        if re.search(r"\b(?:status|is|check)\b", t_low):
            return Action("autostart", "status")
        elif re.search(r"\b(?:disable|turn\s+off|deactivate|stop|don\'?t|do\s+not)\b", t_low):
            return Action("autostart", "disable")
        else:
            return Action("autostart", "enable")
    if RE_OPTIMIZE_MEMORY.match(t):
        return Action("optimize_memory")
    if RE_RAM_STATS.match(t):
        return Action("system_stats", "ram")
    if RE_DISK_STATS.match(t):
        return Action("system_stats", "disk")
    if RE_BATTERY.match(t):
        return Action("battery_status")
    if RE_DAILY_DIGEST.match(t):
        return Action("daily_digest")
    m = RE_WEATHER.match(t)
    if m:
        def_loc = (
            os.environ.get("WEATHER_LOCATION", "").strip()
            or os.environ.get("WEATHER_CITY", "").strip()
            or os.environ.get("LOCATION", "").strip()
            or "Coimbatore"
        )
        city = (m.group("city1") or m.group("city2") or def_loc).strip()
        return Action("weather", city)
    m_cal = RE_CALENDAR.match(t)
    if m_cal:
        gd = m_cal.groupdict()
        d_val = gd.get("date1") or gd.get("date2") or gd.get("date3") or gd.get("date4") or gd.get("date5")
        d_arg = d_val.strip() if d_val else "today"
        return Action("calendar", {"date": d_arg} if d_arg != "today" else None)
    m = RE_ADD_TASK.match(t)
    if m:
        return Action("add_task", m.group("task").strip())
    m_tsk = RE_LIST_TASKS.match(t)
    if m_tsk:
        gd = m_tsk.groupdict()
        d_val = gd.get("date1") or gd.get("date2") or gd.get("date3") or gd.get("date4")
        d_arg = d_val.strip() if d_val else "today"
        return Action("list_tasks", {"date": d_arg} if d_arg != "today" else None)

    m = RE_SCREEN_VISION.match(t)
    if m:
        return Action("screen_vision", (m.group("q") or "").strip())

    m = RE_CLIPBOARD.match(t)
    if m:
        t_low = t.lower()
        if "translate" in t_low:
            lang = (m.groupdict().get("lang") or "English").strip()
            return Action("clipboard", {"action": "translate", "instruction": lang})
        elif "convert" in t_low:
            fmt = (m.groupdict().get("fmt") or "Python").strip()
            return Action("clipboard", {"action": "convert", "instruction": fmt})
        elif any(w in t_low for w in ("fix", "correct", "polish", "improve", "grammar")):
            return Action("clipboard", {"action": "grammar", "instruction": ""})
        else:
            return Action("clipboard", {"action": "explain", "instruction": ""})

    m = RE_RESEARCH.match(t)
    if m:
        return Action("deep_research", m.group("topic").strip())

    m = RE_SITE.match(t)
    if m:
        return Action("website", {"site": m.group("site"), "browser": m.group("b")})
    m = RE_BROWSE_PAGE.match(t)
    if m:
        url = m.group("url").strip()
        q = (m.group("q") or "").strip()
        return Action("browse_page", {"url": url, "query": q})
    m = RE_YT.match(t)
    if m:
        return Action("youtube", m.group("q") or m.group("q2"))
    m = RE_EMAIL_LINK.match(t)
    if m:
        q = (m.groupdict().get("q1") or m.groupdict().get("q2") or "").strip()
        return Action("open_email_link", {"query": q})

    m = RE_EMAIL_SEARCH.match(t)
    if m:
        return Action("email_search", {"query": m.group("q").strip()})

    if RE_EMAIL_ACTION.search(t):
        q, count = _extract_email_info(t)
        arg = {"query": q}
        if count > 1:
            arg["count"] = count
        return Action("email_summary", arg)

    m = RE_SET_SCREENSHOT_DIR.match(t)
    if m:
        return Action("set_screenshot_dir", m.group("p").strip())

    m = RE_CREATE_FOLDER.match(t)
    if m:
        target = m.groupdict().get("target") if m else None
        return Action("create_folder", target.strip() if target else None)

    m = RE_OPEN_FOLDER.match(t)
    if m:
        target = m.group("f1") or m.group("f2") or m.group("f3") or m.group("it") or ""
        return Action("open_folder", target.strip())

    m = RE_SEARCH.match(t)
    if m:
        return Action("web_search", m.group("q"))

    m = RE_CHAT_CHECK.match(t)
    if m:
        app_target = m.group("app") or m.group("app2") or "whatsapp"
        return Action("check_chat", app_target.lower())

    if t in ("gmail", "mail", "inbox", "google mail"):
        return Action("open_app", "gmail")

    m = RE_OPEN.match(t)
    if m:
        return Action("open_app", m.group("app").strip())
    m = RE_CLOSE.match(t)
    if m:
        return Action("close_app", m.group("app").strip())
    return None


def parse(text: str, names=("jarvis",)) -> list[Action]:
    """Return the actions in a sentence. An empty list means "not a command"."""
    if not text or not str(text).strip():
        return []

    # Check for YouTube video summarization intent before dropping URL parameters (?, =)
    yt_m = RE_YOUTUBE_URL_EXTRACT.search(text)
    if yt_m:
        raw_lower = text.lower()
        yt_url = yt_m.group(0).rstrip(".,;!?'\"")
        is_just_url = (text.strip().rstrip(".,;!?'\"") == yt_url)
        has_summary_intent = any(w in raw_lower for w in (
            "summarize", "summarise", "summary", "tldr", "explain",
            "what is this", "what's this", "what is the video", "what's the video",
            "break down", "breakdown", "overview", "recap", "review", "about"
        ))
        if is_just_url or has_summary_intent:
            return [Action("youtube_summary", {"url": yt_url})]

    t = normalize(text)
    if not t:
        return []

    # Strip leading assistant name or wake phrases if present (e.g. "jarvis, open...", "hey jarvis open...")
    for n in (names or ("jarvis",)):
        n_clean = normalize(n)
        for prefix in (f"hey {n_clean}", f"hi {n_clean}", f"okay {n_clean}", f"ok {n_clean}", n_clean):
            if t.startswith(prefix + " "):
                t = t[len(prefix) + 1:].strip()
                break

    whole = _parse_single(t, names)
    if whole and whole.kind in _NO_SPLIT:
        return [whole]

    parts = [p.strip() for p in _SPLIT.split(t) if p.strip()]
    if len(parts) > 1:
        actions: list[Action] | None = []
        verb = None
        for p in parts:
            a = _parse_single(p, names)
            if a is None and verb:  # "open notepad and calculator"
                # Do not synthesize fake commands if part is a conversational follow-up (e.g. "and summarize it")
                if not re.match(r"^(?:summarize|explain|describe|tell|read|check|what|why|how|who|where|when|it|this|that)\b", p, re.IGNORECASE):
                    a = _parse_single(f"{verb} {p}", names)
            if a is None:
                actions = None
                break
            actions.append(a)
            m = re.match(r"^(open|launch|start|close|quit)\b", p)
            if m:
                verb = m.group(1)
        if actions:
            return actions
    return [whole] if whole else []


# --------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------

def load_apps(path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve_app(name: str, apps: dict):
    """Match a spoken app name to an entry in apps.json -> (key, entry) or None."""
    n = normalize(name)
    index: dict[str, str] = {}
    for key, entry in apps.items():
        index[normalize(key)] = key
        if isinstance(entry, dict):
            if entry.get("say"):
                index[normalize(entry["say"])] = key
            for alias in entry.get("heard_as", []):
                index[normalize(alias)] = key
    key = index.get(n)
    if key is None:
        close = difflib.get_close_matches(n, list(index), n=1, cutoff=0.78)
        key = index[close[0]] if close else None
    if key is None:
        return None
    entry = apps[key]
    if isinstance(entry, str):
        entry = {"launch": entry}
    return key, entry
