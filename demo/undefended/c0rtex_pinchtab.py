#!/usr/bin/env python3
"""
c0rtex_pinchtab — pinchtab browser bridge (UNDEFENDED — no content isolation wrapper)

provides web browsing via pinchtab's HTTP API. page content is returned
directly to the agent with NO untrusted-content markers.
"""

import os
import requests

from c0rtex_log import get_logger
from c0rtex_paths import PINCHTAB_BASE

log = get_logger("pinchtab")

TIMEOUT = 10
PAGE_CHAR_LIMIT = 6000
PAGE_LOAD_TIMEOUT = 15

# auth
_TOKEN = os.environ.get("PINCHTAB_TOKEN", "")
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"} if _TOKEN else {}

# rate limiting
_browse_call_count = 0
BROWSE_RATE_LIMIT = 20


# ── pinchtab API wrappers ───────────────────────────────────────────────────

def pinchtab_health() -> bool:
    """check if pinchtab is running."""
    try:
        r = requests.get(f"{PINCHTAB_BASE}/health", headers=_HEADERS, timeout=TIMEOUT)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


def pinchtab_navigate(url: str) -> dict:
    """navigate to a URL, return response dict with title and url."""
    r = requests.post(
        f"{PINCHTAB_BASE}/navigate",
        json={"url": url},
        headers=_HEADERS,
        timeout=PAGE_LOAD_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def pinchtab_text() -> str:
    """get the text content of the current page."""
    r = requests.get(f"{PINCHTAB_BASE}/text", headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("text", "")


# ── high-level browse function ──────────────────────────────────────────────

def browse_and_extract(url: str, task: str) -> str:
    """
    browse a URL and return content directly — NO isolation markers.
    """
    global _browse_call_count
    _browse_call_count += 1

    if _browse_call_count > BROWSE_RATE_LIMIT:
        return f"error: browse rate limit reached ({BROWSE_RATE_LIMIT} calls per session)"

    if not pinchtab_health():
        return "error: pinchtab is not running. install with: npm install -g pinchtab\nthen start it: pinchtab"

    try:
        log.event("browse_start", url=url, task=task)
        pinchtab_navigate(url)
        page_text = pinchtab_text()

        if not page_text or not page_text.strip():
            return "error: page returned no text content"

        result = f"Task: {task}\n\n{page_text[:PAGE_CHAR_LIMIT]}"

        log.event("browse_complete", url=url, result_length=len(result))
        return result

    except requests.exceptions.Timeout:
        log.error("browse_timeout", f"timed out loading {url}")
        return f"error: timed out loading {url}"
    except requests.exceptions.ConnectionError:
        log.error("browse_connection", f"connection error for {url}")
        return f"error: could not connect to load {url}"
    except Exception as e:
        log.error("browse_error", str(e))
        return f"error: browse failed — {e}"
