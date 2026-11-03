"""Answers questions and runs multi-step agent tasks through Gemini Native or OpenAI-compatible APIs."""
from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_PROMPT = (
    "You are {name}, an AI assistant on the user's Windows PC. "
    "Your responses are read aloud, so answer concisely in one to three plain sentences with no markdown or emojis. "
    "You have tools to control Windows, check battery diagnostics and power status, launch applications, create and open folders, take screenshots, search emails, browse the web, play YouTube videos, provide daily digests, and adjust system settings. "
    "When asked to perform tasks on the computer, invoke the appropriate tool. Never search the web for Windows system commands or folder creation. "
    "When the user asks to open or summarize a repository, website, guide, or online resource (such as 'open genspark ai repo on brave and summarize it'), invoke browse_web_page (with the browser parameter if a browser like Brave or Chrome was mentioned) to automatically locate the link, launch it in their browser, and summarize the contents. Do not ask for confirmation if the user directly commanded to open and summarize it. "
    "For chat applications like WhatsApp, Telegram, or Signal, explain that messages are end-to-end encrypted on the device and cannot be intercepted in the background, and invoke open_app to bring up the application on screen."
)

# --------------------------------------------------------------------------
# Native Gemini Tool Schema
# --------------------------------------------------------------------------
GEMINI_TOOLS = [{
    "function_declarations": [
        {
            "name": "play_youtube_video",
            "description": "Play a YouTube video, the latest upload, or the most viewed/popular video from a channel (e.g. 'sadhguru') in a browser.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query_or_channel": {"type": "STRING", "description": "Channel name or search query, e.g. 'sadhguru'"},
                    "sort_by": {"type": "STRING", "enum": ["latest", "views", "relevance"], "description": "Sort mode: 'latest' for newest, 'views' for most viewed/popular, 'relevance' for top result"},
                    "browser": {"type": "STRING", "description": "Browser name, e.g. 'brave', 'chrome', 'edge'"}
                },
                "required": ["query_or_channel"]
            }
        },
        {
            "name": "read_and_summarize_email",
            "description": "Read, check, and summarize the latest email(s) from inbox or matching a query or sender. Use count to specify how many emails to summarize (e.g. 1, 3, 5). ALWAYS use this tool when the user asks to summarize, check, read, or see emails or inbox content, rather than searching in browser.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "Subject, sender, or keyword to search for, or empty string for all latest inbox emails."},
                    "count": {"type": "INTEGER", "description": "Number of emails to fetch and summarize (e.g. 1, 3, 5). Default is 1."}
                }
            }
        },
        {
            "name": "search_email",
            "description": "Open Gmail or Outlook in a web browser window. ONLY use this when user explicitly asks to open their browser, launch the mail app, or search on screen, NOT when they ask Jarvis to read or summarize emails.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "The search term or topic to find in emails, e.g. 'samyama'"},
                    "provider": {"type": "STRING", "enum": ["gmail", "outlook"], "description": "Email provider: 'gmail' (default) or 'outlook'"},
                    "browser": {"type": "STRING", "description": "Browser to use, e.g. 'brave', 'chrome'"}
                }
            }
        },
        {
            "name": "open_email_link",
            "description": "Find and open a link, portal link, or website mentioned in an email matching a query or sender directly in the browser. Use this whenever the user asks to open a link, portal link, or website mentioned in or from an email.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "Sender, subject, or keywords from the email to find the link in, e.g. 'isha foundation' or 'support portal'"}
                }
            }
        },
        {
            "name": "browse_web_page",
            "description": "Browse, read, inspect, or summarize live content from a website URL, online repository, or topic (e.g. 'genspark ai repo', 'https://github.com/...'). Automatically locates the link, opens it in the specified browser (if requested), and summarizes the content.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url": {"type": "STRING", "description": "The web page URL, repository name, or search query to browse, e.g. 'genspark ai repo' or 'https://github.com/...'"},
                    "query": {"type": "STRING", "description": "Optional specific question or details to extract from the page."},
                    "browser": {"type": "STRING", "description": "Optional browser name to launch the page in simultaneously, e.g. 'brave', 'chrome', 'edge'"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "screen_vision",
            "description": "Visually inspect, analyze, or explain what is currently displayed on the user's computer screen or active window. Use this whenever the user asks 'look at my screen', 'what is on my screen', 'explain this error', 'check this code/chart on screen', etc.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "prompt": {"type": "STRING", "description": "Specific question or analysis request regarding the screen content"}
                }
            }
        },
        {
            "name": "clipboard_action",
            "description": "Read, explain, summarize, translate, polish, or convert text currently copied on the user's clipboard. Use this whenever the user asks to explain, summarize, fix grammar of, translate, or format what they just copied.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {"type": "STRING", "enum": ["explain", "summarize", "fix", "grammar", "translate", "convert", "format"], "description": "Action to perform on clipboard text"},
                    "instruction": {"type": "STRING", "description": "Optional specific instructions or target language"}
                },
                "required": ["action"]
            }
        },
        {
            "name": "deep_research",
            "description": "Execute autonomous multi-source deep web research on any topic using Lightpanda and synthesize a formal technical dossier saved to Documents/Jarvis. Use this whenever the user asks to research, do a deep dive, or investigate a topic.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING", "description": "The topic, company, concept, or technical subject to research"}
                },
                "required": ["topic"]
            }
        },
        {
            "name": "open_website",
            "description": "Open a website URL in a specific browser (e.g. 'brave', 'chrome', 'edge') or default browser.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "url": {"type": "STRING", "description": "The URL to open, e.g. 'https://youtube.com'"},
                    "browser": {"type": "STRING", "description": "Browser name like 'brave', 'chrome', 'edge'"}
                },
                "required": ["url"]
            }
        },
        {
            "name": "open_app",
            "description": "Launch any desktop application (e.g. 'brave', 'chrome', 'notepad', 'spotify', 'calculator', 'slack').",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "app_name": {"type": "STRING", "description": "Name of the app to launch."}
                },
                "required": ["app_name"]
            }
        },
        {
            "name": "close_app",
            "description": "Close a running application.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "app_name": {"type": "STRING", "description": "Name of the app to close."}
                },
                "required": ["app_name"]
            }
        },
        {
            "name": "control_volume",
            "description": "Set system volume level (0-100), adjust volume step up/down (+10, -10), or mute/unmute.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "level": {"type": "INTEGER", "description": "Exact volume level from 0 to 100"},
                    "step": {"type": "INTEGER", "description": "Relative volume step (+10, -10, etc.)"},
                    "mute": {"type": "BOOLEAN", "description": "True to mute, False to unmute"}
                }
            }
        },
        {
            "name": "media_control",
            "description": "Control music and media playback: 'play_pause', 'next', 'previous'.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {"type": "STRING", "enum": ["play_pause", "next", "previous"]}
                },
                "required": ["action"]
            }
        },
        {
            "name": "set_timer",
            "description": "Create a timer or reminder for a number of seconds.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "seconds": {"type": "INTEGER", "description": "Number of seconds."},
                    "label": {"type": "STRING", "description": "What the timer or reminder is for."}
                },
                "required": ["seconds"]
            }
        },
        {
            "name": "web_search",
            "description": "Search Google or the web for general information.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING", "description": "Search term."}
                },
                "required": ["query"]
            }
        },
        {
            "name": "create_folder",
            "description": "Create a new folder or directory on Windows (e.g. in Pictures, Documents, Desktop, Downloads).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "path_or_name": {"type": "STRING", "description": "Folder path or name, e.g. 'Pictures/Jarvis' or 'Jarvis'"}
                },
                "required": ["path_or_name"]
            }
        },
        {
            "name": "open_folder",
            "description": "Open a folder in Windows File Explorer (e.g. 'Pictures', 'Jarvis', 'Downloads', 'Documents').",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "folder_name": {"type": "STRING", "description": "Name or path of folder to open in File Explorer."}
                },
                "required": ["folder_name"]
            }
        },
        {
            "name": "system_control",
            "description": "Execute system action: 'lock', 'sleep' (computer sleep), 'standby' (put Jarvis to sleep/standby), 'show_desktop', 'screenshot', 'dark_mode', 'light_mode'.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "action": {"type": "STRING", "enum": ["lock", "sleep", "standby", "show_desktop", "screenshot", "dark_mode", "light_mode"]}
                },
                "required": ["action"]
            }
        },
        {
            "name": "get_time_date",
            "description": "Get the current time and date.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        },
        {
            "name": "get_system_stats",
            "description": "Get real-time system performance telemetry: CPU utilization %, logical core count, RAM/memory usage (GB and %), local drive C storage, and battery state.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "category": {
                        "type": "STRING",
                        "enum": ["all", "cpu", "ram", "memory", "disk", "storage", "battery"],
                        "description": "Specific telemetry subsystem to query ('all', 'cpu', 'ram', 'disk', 'battery'). Defaults to 'all'."
                    }
                }
            }
        },
        {
            "name": "get_battery_status",
            "description": "Get the current system battery level, charging state, and remaining runtime life estimate.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        },
        {
            "name": "get_daily_digest",
            "description": "Provide a comprehensive daily briefing or morning digest covering Coimbatore weather, today's calendar schedule, and the latest 3 emails from inbox. ALWAYS use this tool whenever the user asks for a daily digest, morning briefing, briefing, or summary of their day.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        },
        {
            "name": "get_weather",
            "description": "Get current weather condition, temperature, feels-like, and humidity for a specified city (default: Coimbatore).",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "city": {"type": "STRING", "description": "City name, e.g. 'Coimbatore', 'London', 'New York'. Defaults to 'Coimbatore'."}
                }
            }
        },
        {
            "name": "get_calendar_events",
            "description": "Check and retrieve scheduled calendar events, appointments, and active tasks for today.",
            "parameters": {
                "type": "OBJECT",
                "properties": {}
            }
        }
    ]
}]

# --------------------------------------------------------------------------
# Standard OpenAI Tool Schema (for OpenRouter / Ollama fallback)
# --------------------------------------------------------------------------
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": decl["name"],
            "description": decl["description"],
            "parameters": {
                "type": "object",
                "properties": {
                    k: {**v, "type": v["type"].lower()} for k, v in decl["parameters"].get("properties", {}).items()
                },
                "required": decl["parameters"].get("required", [])
            }
        }
    }
    for decl in GEMINI_TOOLS[0]["function_declarations"]
]


class LLM:
    def __init__(self, api_key: str, base_url: str, model: str, name: str = "Jarvis"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model or "gemini-3.5-flash"
        self.name = name
        self.history: list[dict] = []
        self.is_gemini = "generativelanguage.googleapis.com" in self.base_url

    def ask(self, question: str) -> str:
        """Simple plain text question answering without tools."""
        if not self.api_key:
            return "I can answer questions once you add an API key to the dot env file."
        import requests

        if self.is_gemini:
            payload = {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT.format(name=self.name)}]},
                "contents": [{"role": "user", "parts": [{"text": question}]}],
                "generationConfig": {
                    "maxOutputTokens": 600,
                    "thinkingConfig": {"thinkingBudget": 0}
                }
            }
            models_to_try = [self.model]
            for alt in ("gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"):
                if alt not in models_to_try:
                    models_to_try.append(alt)

            last_err = None
            for model_candidate in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_candidate}:generateContent?key={self.api_key}"
                try:
                    for attempt in range(2):
                        try:
                            r = requests.post(url, json=payload, timeout=35)
                            if r.status_code in (503, 429) and attempt < 1:
                                import time
                                time.sleep(1.2)
                                continue
                            r.raise_for_status()
                            break
                        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                            if attempt < 1:
                                import time
                                time.sleep(1.2)
                                continue
                            raise
                    data = r.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    text_parts = [p.get("text", "").strip() for p in parts if "text" in p]
                    answer = " ".join(t for t in text_parts if t)
                    if not answer:
                        answer = "At your service, sir."
                    answer = re.sub(r"[*_#`]", "", answer)
                    self.history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
                    return answer
                except Exception as e:
                    last_err = e
                    continue

            print(f"  [llm error] {last_err!r}")
            return "Sorry, I couldn't reach the question service."

        # OpenAI-compatible fallback
        messages = [{"role": "system", "content": SYSTEM_PROMPT.format(name=self.name)},
                    *self.history[-6:], {"role": "user", "content": question}]
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "max_tokens": 250},
                timeout=35,
            )
            r.raise_for_status()
            answer = r.json()["choices"][0]["message"]["content"].strip()
            self.history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            return answer
        except Exception as e:
            print(f"  [llm error] {e!r}")
            return "Sorry, I couldn't reach the question service."

    def agent_run(self, prompt: str, ctx) -> str:
        """Agentic loop: executes multi-step tasks using tool calling."""
        if not self.api_key:
            return "I need an API key configured to execute advanced or multi-step tasks."
        import requests
        from actions import execute_tool

        # --- NATIVE GEMINI IMPLEMENTATION (Fast, robust, zero timeout) ---
        if self.is_gemini:
            payload = {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT.format(name=self.name)}]},
                "contents": [
                    *[
                        {"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["content"]}]}
                        for h in self.history[-4:]
                    ],
                    {"role": "user", "parts": [{"text": prompt}]}
                ],
                "tools": GEMINI_TOOLS,
                "generationConfig": {
                    "maxOutputTokens": 600,
                    "thinkingConfig": {"thinkingBudget": 0}
                }
            }

            models_to_try = [self.model]
            for alt in ("gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"):
                if alt not in models_to_try:
                    models_to_try.append(alt)

            last_err = None
            for model_candidate in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_candidate}:generateContent?key={self.api_key}"
                try:
                    for attempt in range(2):
                        try:
                            r = requests.post(url, json=payload, timeout=35)
                            if r.status_code in (503, 429) and attempt < 1:
                                import time
                                time.sleep(1.2)
                                continue
                            r.raise_for_status()
                            break
                        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                            if attempt < 1:
                                import time
                                time.sleep(1.2)
                                continue
                            raise
                    data = r.json()
                    candidate = data["candidates"][0]
                    parts = candidate.get("content", {}).get("parts", [])

                    executed_replies: list[str] = []
                    for p in parts:
                        if "functionCall" in p:
                            fn = p["functionCall"]
                            fn_name = fn.get("name", "")
                            fn_args = fn.get("args", {})
                            result = execute_tool(fn_name, fn_args, ctx)
                            if result:
                                executed_replies.append(result)

                    if executed_replies:
                        summary = " ".join(executed_replies)
                        self.history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": summary}]
                        return summary

                    # Plain text reply
                    text_parts = [p.get("text", "").strip() for p in parts if "text" in p]
                    answer = " ".join(t for t in text_parts if t)
                    if not answer:
                        answer = "At your service, sir."
                    answer = re.sub(r"[*_#`]", "", answer)
                    self.history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}]
                    return answer
                except Exception as e:
                    last_err = e
                    continue

            print(f"  [agent error] {last_err!r}")
            p_lower = prompt.lower()
            if any(w in p_lower for w in ("daily digest", "morning digest", "digest", "brief me", "morning briefing", "daily briefing")):
                return execute_tool("daily_digest", {}, ctx)
            if "weather" in p_lower:
                return execute_tool("weather", {"city": "Coimbatore"}, ctx)
            if "calendar" in p_lower:
                return execute_tool("calendar", {}, ctx)
            if any(w in p_lower for w in ("create folder", "make folder", "create that folder", "do it for me", "create it for me")):
                return execute_tool("create_folder", {"path_or_name": "Pictures/Jarvis"}, ctx)
            if any(w in p_lower for w in ("open folder", "open pictures", "open jarvis")):
                return execute_tool("open_folder", {"folder_name": "jarvis"}, ctx)
            if any(w in p_lower for w in ("email", "emails", "inbox", "samyama", "application", "mail")):
                from commands import _extract_email_info
                q, count = _extract_email_info(prompt)
                return execute_tool("read_and_summarize_email", {"query": q, "count": count}, ctx)
            if "youtube" in p_lower:
                return execute_tool("play_youtube_video", {"query_or_channel": prompt}, ctx)
            if any(w in p_lower for w in ("search", "google", "look up", "find")):
                return execute_tool("web_search", {"query": prompt}, ctx)
            return "I apologize, sir. I had trouble connecting to the network."

        # --- OPENAI-COMPATIBLE FALLBACK ---
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(name=self.name)},
            *self.history[-4:],
            {"role": "user", "content": prompt}
        ]

        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "tools": OPENAI_TOOLS, "max_tokens": 300},
                timeout=35,
            )
            r.raise_for_status()
            choice = r.json()["choices"][0]
            msg = choice.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                content = (msg.get("content") or "").strip() or "At your service, sir."
                self.history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": content}]
                return content

            executed_replies: list[str] = []
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    fn_args = json.loads(raw_args)
                except Exception:
                    fn_args = {}
                result = execute_tool(fn_name, fn_args, ctx)
                if result:
                    executed_replies.append(result)

            if executed_replies:
                summary = " ".join(executed_replies)
                self.history += [{"role": "user", "content": prompt}, {"role": "assistant", "content": summary}]
                return summary

            return "Done, sir."

        except Exception as e:
            print(f"  [agent error] {e!r}")
            return "I apologize, sir. I had trouble connecting to the network."
