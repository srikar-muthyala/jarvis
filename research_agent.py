"""Deep Web Research Agent for Jarvis powered by Lightpanda and Gemini."""
from __future__ import annotations

import datetime
import os
import re
import urllib3
urllib3.disable_warnings()
from pathlib import Path

from lightpanda_browser import fetch_url_markdown


def get_documents_jarvis_dir() -> Path:
    """Return path to Documents/Jarvis directory."""
    import ctypes
    docs = Path.home() / "Documents"
    if hasattr(ctypes, "windll"):
        try:
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
            if buf.value:
                docs = Path(buf.value)
        except Exception:
            pass
    target = docs / "Jarvis"
    target.mkdir(parents=True, exist_ok=True)
    return target


def deep_research_topic(topic: str, ctx) -> tuple[str, str]:
    """Perform deep multi-source research on topic using Lightpanda and Gemini.

    Returns tuple: (spoken_summary, path_to_saved_report)
    """
    clean_topic = topic.strip()
    if not clean_topic:
        return ("Please specify a topic for me to research, sir.", "")

    ctx.do(f"conduct deep research on {clean_topic}")

    # 1. Search web for authoritative sources
    import requests
    import html

    urls: list[str] = []
    try:
        r = requests.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": clean_topic},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            verify=False,
            timeout=8
        )
        if r.status_code == 200:
            raw_links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\']', r.text)
            junk_domains = ("duckduckgo.com", "bing.com", "google.com", "yandex.com", "yahoo.com")
            for link in raw_links:
                if link.startswith("//"):
                    link = "https:" + link
                elif link.startswith("/"):
                    continue
                if not link.startswith("http"):
                    continue
                if any(j in link.lower() for j in junk_domains):
                    continue
                clean_link = html.unescape(link)
                if clean_link not in urls:
                    urls.append(clean_link)
                if len(urls) >= 4:
                    break
    except Exception as e:
        print(f"  [research search error: {e}]")

    # 2. Browse each source with Lightpanda to extract rendered markdown
    sources_data: list[dict[str, str]] = []
    for u in urls[:3]:
        try:
            content = fetch_url_markdown(u, timeout_sec=10, max_chars=3000)
            if content and not content.startswith("Unable to retrieve"):
                sources_data.append({"url": u, "content": content})
        except Exception:
            pass

    combined_notes = ""
    for idx, s in enumerate(sources_data, 1):
        combined_notes += f"\n\n--- Source {idx}: {s['url']} ---\n{s['content'][:2500]}"

    llm = getattr(ctx, "llm", None)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    slug = re.sub(r"[^\w\-_]+", "_", clean_topic.lower())[:30]

    if llm:
        # 3. Synthesize deep structured report using document writer (never truncated or voice-limited)
        report_prompt = (
            f"Synthesize an authoritative, exhaustive executive research dossier on '{clean_topic}'.\n\n"
            f"GATHERED RESEARCH NOTES:\n{combined_notes}\n\n"
            f"Format as an executive Markdown dossier with sections: Executive Summary, Strategic & Historical Architecture, "
            f"Key Turning Points & Tactical Dilemmas, Executive Lessons for Modern Leadership, and Concluding Analysis."
        )
        if hasattr(llm, "synthesize_document"):
            report_md = llm.synthesize_document(report_prompt)
        else:
            report_md = ""

        if not report_md or len(report_md) < 200:
            report_md = (
                f"# Executive Dossier: {clean_topic.title()}\n\n"
                f"**Generated:** {timestamp} | **Analyst:** J.A.R.V.I.S. Executive Intelligence\n\n"
                f"## 1. Executive Summary\n\n"
                f"A comprehensive examination of '{clean_topic}' encompassing core strategic, historical, and philosophical frameworks.\n\n"
                f"## 2. Gathered Research Findings\n{combined_notes}\n"
            )

        # 4. Separate spoken summary tailored strictly for natural voice readout
        spoken_prompt = (
            f"Based on your complete research on '{clean_topic}', deliver an executive spoken briefing to Tony Stark in 2 concise sentences without markdown or asterisks."
        )
        spoken_summary = llm.ask(spoken_prompt).strip()
    else:
        report_md = f"# Research Dossier: {clean_topic.title()}\nGenerated on {timestamp}\n\n"
        if sources_data:
            report_md += f"## Gathered Findings\n{combined_notes}\n"
        else:
            report_md += "No external web sources were reachable."
        spoken_summary = f"I have compiled the available research on {clean_topic}, sir."

    # Save dossier to Documents/Jarvis
    doc_dir = get_documents_jarvis_dir()
    file_path = doc_dir / f"research_{slug}.md"
    file_path.write_text(report_md, encoding="utf-8")

    spoken_summary += f" I have compiled the complete dossier and saved it to your Documents Jarvis directory."
    return (spoken_summary, str(file_path))
