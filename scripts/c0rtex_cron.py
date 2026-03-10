#!/usr/bin/env python3
"""
c0rtex cron — runs prompts through ollama and sends results to matrix.
used for morning briefings, school reminders, and scheduled checks.

usage:
    python c0rtex_cron.py briefing
    python c0rtex_cron.py deadlines
    python c0rtex_cron.py "any custom prompt here"
"""

import json
import sys
import time
import requests
from datetime import datetime, timedelta
from c0rtex_log import get_logger
from c0rtex_tools import TOOLS, execute_tool
from c0rtex_paths import (
    SOUL_FILE, SCHOOL_FILE, USERNAME,
    OLLAMA_HOST, MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
)

log = get_logger("cron")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "c0rtex"

# ── soul ────────────────────────────────────────────────────────────────────

DEFAULT_SOUL = f"""you are c0rtex, {USERNAME}'s personal ai assistant and digital ghost.
you speak in all lowercase. you're casual, sharp, and a little sarcastic.
today's date is {{date}}.
"""


def load_soul():
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text()
    else:
        soul = DEFAULT_SOUL
    return soul.replace("{date}", datetime.now().strftime("%A, %B %d, %Y"))


# ── tools (imported from c0rtex_tools — guardrailed set) ──────────────────
# TOOLS and execute_tool are imported at the top from c0rtex_tools.


# ── ollama ──────────────────────────────────────────────────────────────────

def chat_ollama(messages: list) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "tools": TOOLS,
        "options": {"num_ctx": 8192}
    }
    log.ollama_request(MODEL, messages, tools=True)
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        tc_names = [tc["function"]["name"] for tc in (msg.get("tool_calls") or [])]
        log.ollama_response(MODEL, msg.get("content", ""), int((time.time() - t0) * 1000),
                            tool_call_names=tc_names)
        return msg
    except Exception as e:
        log.error("ollama", str(e))
        return {"role": "assistant", "content": f"something broke: {e}"}


def get_response(prompt: str) -> str:
    """run a prompt through the tool-calling loop and return final text."""
    soul = load_soul()
    messages = [
        {"role": "system", "content": soul},
        {"role": "user", "content": prompt}
    ]

    for _ in range(10):
        msg = chat_ollama(messages)
        tool_calls = msg.get("tool_calls")

        if tool_calls:
            messages.append(msg)
            for tool_call in tool_calls:
                func = tool_call["function"]
                name = func["name"]
                args = func.get("arguments", {})
                log.tool_call(name, args)
                _t = time.time()
                result = execute_tool(name, args)
                log.tool_result(name, result, int((time.time() - _t) * 1000))
                messages.append({"role": "tool", "content": result})
            continue
        else:
            return msg.get("content", "...")

    return "hit tool call limit."


# ── matrix ──────────────────────────────────────────────────────────────────

def send_matrix_message(message: str):
    """send a message to the c0rtex matrix room."""
    url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{MATRIX_ROOM_ID}/send/m.room.message"
    headers = {
        "Authorization": f"Bearer {MATRIX_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "msgtype": "m.text",
        "body": message
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"failed to send matrix message: {e}")


# ── deadline checker ────────────────────────────────────────────────────────

def check_deadlines() -> str:
    """check SCHOOL.md for upcoming deadlines and return a summary."""
    if not SCHOOL_FILE.exists():
        return None

    school = SCHOOL_FILE.read_text()
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    week_out = today + timedelta(days=7)

    today_str = today.strftime("%Y-%m-%d")
    tomorrow_str = tomorrow.strftime("%Y-%m-%d")

    # find unchecked items with dates in the next 7 days
    urgent = []      # today or tomorrow
    upcoming = []     # next 2-7 days

    for line in school.split("\n"):
        line = line.strip()
        if not line.startswith("- [ ]"):
            continue

        # try to find a date in the line
        import re
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if not date_match:
            continue

        try:
            due_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
        except ValueError:
            continue

        # skip past dates
        if due_date.date() < today.date():
            continue

        item = line.replace("- [ ] ", "").strip()
        days_until = (due_date.date() - today.date()).days

        if days_until <= 1:
            urgent.append(f"  DUE {'TODAY' if days_until == 0 else 'TOMORROW'}: {item}")
        elif days_until <= 7:
            upcoming.append(f"  due in {days_until} days: {item}")

    if not urgent and not upcoming:
        return None

    parts = []
    if urgent:
        parts.append("URGENT:\n" + "\n".join(urgent))
    if upcoming:
        parts.append("coming up:\n" + "\n".join(upcoming))

    return "\n\n".join(parts)


# ── prompts ─────────────────────────────────────────────────────────────────

BRIEFING_PROMPT = """give the morning briefing. keep it tight and useful. include:
- what day it is and what's on the schedule today
- any deadlines coming up this week (check the info below)
- a quick motivational nudge if something big is due soon

here are the upcoming deadlines:
{deadlines}

keep it short. no fluff. just what needs to be known."""

DEADLINE_PROMPT = """there are upcoming school deadlines. give a quick heads up about what's due soon.
be direct, no fluff, just the deadlines and what needs to be done.

{deadlines}"""


# ── main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("usage: python c0rtex_cron.py [briefing|deadlines|\"custom prompt\"]")
        sys.exit(1)

    mode = " ".join(sys.argv[1:])
    log.session_start(mode=mode)
    try:
        _run(mode)
    finally:
        log.session_end()


def _run(mode: str):

    if mode == "briefing":
        deadlines = check_deadlines() or "nothing urgent this week."
        prompt = BRIEFING_PROMPT.replace("{deadlines}", deadlines)
        response = get_response(prompt)
        send_matrix_message(response)
        print(f"sent briefing: {response[:100]}...")

    elif mode == "deadlines":
        deadlines = check_deadlines()
        if deadlines:
            prompt = DEADLINE_PROMPT.replace("{deadlines}", deadlines)
            response = get_response(prompt)
            send_matrix_message(response)
            print(f"sent deadline reminder: {response[:100]}...")
        else:
            print("no upcoming deadlines, skipping.")

    else:
        # custom prompt mode
        response = get_response(mode)
        send_matrix_message(response)
        print(f"sent: {response[:100]}...")


if __name__ == "__main__":
    main()
