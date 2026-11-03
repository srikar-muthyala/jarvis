"""Lightpanda headless browser client for Jarvis.

Ultra-fast, low-memory browser execution using Lightpanda via CLI or CDP.
Renders modern dynamic JavaScript websites and returns clean Markdown.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN_PATH = HERE / "bin" / "lightpanda"


def is_wsl_available() -> bool:
    """Check if WSL is installed and functional."""
    try:
        r = subprocess.run(["wsl", "echo", "ok"], capture_output=True, text=True, timeout=3)
        return r.returncode == 0 and "ok" in r.stdout
    except Exception:
        return False


def get_wsl_path(windows_path: Path) -> str:
    """Convert Windows path C:\\... to WSL /mnt/c/... path."""
    resolved = str(windows_path.resolve())
    drive = resolved[0].lower()
    rest = resolved[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def fetch_url_markdown(url: str, timeout_sec: int = 12, max_chars: int = 4000) -> str:
    """Fetch URL and return rendered Markdown using Lightpanda.

    Falls back to requests + plain text extraction if Lightpanda is unavailable.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # 1. Native Linux execution
    if sys.platform != "win32":
        bin_to_use = str(BIN_PATH) if BIN_PATH.exists() else shutil.which("lightpanda")
        if bin_to_use:
            try:
                cmd = [
                    bin_to_use, "fetch", url, "--dump", "markdown",
                    "--strip-mode", "clutter", "--terminate-ms", str(timeout_sec * 1000)
                ]
                res = subprocess.run(
                    cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout_sec + 3
                )
                if res.returncode == 0 and res.stdout.strip():
                    content = res.stdout.strip()
                    content = re.sub(r"\n{3,}", "\n\n", content)
                    if len(content) > max_chars:
                        content = content[:max_chars] + "\n... [content truncated]"
                    return content
            except Exception as e:
                print(f"  [lightpanda native error: {e}]")

    # 2. Windows execution via WSL
    elif BIN_PATH.exists() and is_wsl_available():
        try:
            wsl_bin = get_wsl_path(BIN_PATH)
            # Make sure binary is executable
            subprocess.run(["wsl", "chmod", "+x", wsl_bin], capture_output=True, timeout=3)

            cmd = [
                "wsl", "bash", "-c",
                f"'{wsl_bin}' fetch '{url}' --dump markdown --strip-mode clutter --terminate-ms {timeout_sec * 1000}"
            ]
            res = subprocess.run(
                cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout_sec + 3
            )
            if res.returncode == 0 and res.stdout.strip():
                content = res.stdout.strip()
                # Clean multiple empty lines
                content = re.sub(r"\n{3,}", "\n\n", content)
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... [content truncated]"
                return content
        except Exception as e:
            print(f"  [lightpanda error: {e}]")

    # 2. Try Playwright connect over CDP if Lightpanda CDP server is running
    cdp_url = os.environ.get("LIGHTPANDA_CDP_URL", "http://127.0.0.1:8888")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url, timeout=3000)
            page = browser.new_page()
            page.goto(url, timeout=timeout_sec * 1000)
            text = page.inner_text("body")
            browser.close()
            if text.strip():
                return text.strip()[:max_chars]
    except Exception:
        pass

    # 3. Fallback: Fast HTTP request
    try:
        import urllib3
        urllib3.disable_warnings()
        import requests

        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, verify=False, timeout=timeout_sec)
        if r.status_code == 200:
            text = r.text
            # Basic HTML to clean text
            text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]
    except Exception:
        pass

    return f"Unable to retrieve content from {url}."
