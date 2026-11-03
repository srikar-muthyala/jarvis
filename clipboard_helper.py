"""Clipboard helper for reading, transforming, and updating Windows clipboard."""
from __future__ import annotations

import re
import pyperclip


def get_clipboard() -> str:
    """Read text from clipboard safely."""
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def set_clipboard(text: str) -> bool:
    """Set text on clipboard safely."""
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def process_clipboard(action_type: str, custom_instruction: str, llm) -> tuple[str, str]:
    """Process clipboard content using Gemini.

    Returns tuple: (spoken_summary, new_clipboard_content)
    """
    text = get_clipboard().strip()
    if not text:
        return ("Your clipboard is currently empty, sir.", "")

    if not llm:
        return ("I need an LLM API key configured to transform your clipboard, sir.", "")

    # Truncate input if excessively large
    input_text = text[:4000]

    action_type = action_type.lower()
    if action_type in ("explain", "summarize"):
        prompt = (
            f"The user asked to explain or summarize their clipboard text:\n\n"
            f"```\n{input_text}\n```\n\n"
            f"Summarize or explain this clearly in 2 to 3 spoken sentences without markdown or asterisks."
        )
        answer = llm.ask(prompt)
        return (answer.strip(), text)

    elif action_type in ("fix", "grammar", "improve", "polish"):
        prompt = (
            f"Improve, polish, and fix the grammar and tone of this text. Return ONLY the improved replacement text without quotes or explanations:\n\n"
            f"{input_text}"
        )
        improved = llm.ask(prompt).strip()
        set_clipboard(improved)
        return ("I have polished the text and updated your clipboard, sir.", improved)

    elif action_type in ("translate", "translation"):
        target_lang = custom_instruction or "English"
        prompt = (
            f"Translate this text to {target_lang}. Return ONLY the translated replacement text without commentary:\n\n"
            f"{input_text}"
        )
        translated = llm.ask(prompt).strip()
        set_clipboard(translated)
        return (f"I have translated the text to {target_lang} and updated your clipboard, sir.", translated)

    elif action_type in ("code", "convert", "format"):
        prompt = (
            f"User instruction: {custom_instruction or 'Convert or format this code cleanly'}\n\n"
            f"Clipboard code/data:\n```\n{input_text}\n```\n\n"
            f"Return ONLY the converted/formatted code or data without markdown backticks or explanations."
        )
        converted = llm.ask(prompt).strip()
        set_clipboard(converted)
        return ("I have converted the code and placed the result onto your clipboard, sir.", converted)

    else:
        prompt = (
            f"Apply this instruction: '{custom_instruction}' to the following clipboard content:\n\n"
            f"{input_text}\n\n"
            f"Return ONLY the result without commentary."
        )
        result = llm.ask(prompt).strip()
        set_clipboard(result)
        return ("I have processed your clipboard according to your instructions, sir.", result)
