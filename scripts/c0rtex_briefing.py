#!/usr/bin/env python3
"""
c0rtex briefing — morning briefing with thinking enabled.
reads SCHOOL.md, reasons about dates, sends result to matrix.
"""

import time
import requests
from datetime import datetime
from c0rtex_log import get_logger
from pathlib import Path
from c0rtex_paths import (
    SCHOOL_FILE, SOUL_FILE, USERNAME,
    OLLAMA_HOST, MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
)

log = get_logger("briefing")

MODEL = "qwen3:32b"


def send_matrix_message(message: str):
    url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{MATRIX_ROOM_ID}/send/m.room.message"
    headers = {
        "Authorization": f"Bearer {MATRIX_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"msgtype": "m.text", "body": message}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"failed to send matrix message: {e}")


def load_file(path: Path) -> str:
    if path.exists():
        return path.read_text()
    return ""


def chat_ollama(messages: list) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": True,
        "options": {"num_ctx": 8192}
    }
    log.ollama_request(MODEL, messages, think=True)
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        content = msg.get("content", "...")
        log.ollama_response(MODEL, content, int((time.time() - t0) * 1000),
                            thinking=msg.get("thinking"))
        return content
    except Exception as e:
        log.error("ollama", str(e))
        return f"something broke: {e}"


def main():
    log.session_start()
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    day_name = now.strftime("%A")

    school = load_file(SCHOOL_FILE)

    if not school:
        send_matrix_message("couldn't find SCHOOL.md — no briefing today.")
        return

    # try to get oura ring data for the briefing
    oura_section = ""
    try:
        from c0rtex_oura import get_daily_summary
        oura_data = get_daily_summary()
        if oura_data:
            oura_section = f"""

here is oura ring data from last night:

{oura_data}

6. if oura data is available, briefly mention the sleep and readiness scores. just report the numbers, don't give health advice."""
    except Exception:
        pass

    prompt = f"""you are c0rtex, {USERNAME}'s ai assistant. today is {date_str}.

here is the complete school schedule and deadlines:

{school}

give {USERNAME} the morning briefing. be precise and careful with dates. follow these rules exactly:

1. state what day it is.
2. list which classes are on TODAY based on the schedule.
3. list deadlines that are due THIS WEEK (between today and the next 7 days). for each one:
   - say the exact class name
   - say the exact due date
   - say if its already passed or still upcoming
   - only include items marked with [ ] (unchecked). skip items marked [x] (completed).
4. if any exams are coming up within 2 weeks, mention them.
5. add any relevant notes from the notes section at the bottom of the school file.{oura_section}

CRITICAL RULES:
- do NOT invent dates. only use dates that appear in the school file above.
- do NOT guess quiz or assignment numbers. read them exactly from the file.
- if an item's date has already passed (before {date_str}), say "already passed" — do NOT move it to a future date.
- write conversationally like a text message. no markdown headers, no bold, no asterisks, no bullet formatting. just plain lowercase text.
- be specific about which class each item belongs to.
- keep it concise."""

    response = chat_ollama([{"role": "user", "content": prompt}])
    send_matrix_message(response)
    log.matrix_out(response)
    print(f"briefing sent: {response[:100]}...")
    log.session_end()


if __name__ == "__main__":
    main()

