#!/usr/bin/env python3
"""
c0rtex deadline check — evening check for upcoming deadlines.
parses SCHOOL.md for real dates, only alerts via matrix when something is actually due.
"""

import re
import time
import requests
from datetime import datetime, timedelta
from c0rtex_log import get_logger
from c0rtex_paths import (
    SCHOOL_FILE, USERNAME,
    OLLAMA_HOST, MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
)

log = get_logger("deadlines")

MODEL = "qwen3:32b"

# matches unchecked items with a date: "- [ ] description - Due 2026-03-09" or "- [ ] description - 2026-03-09"
DEADLINE_RE = re.compile(
    r"^- \[ \] (.+?)(?:\s*-\s*(?:Due\s+)?(\d{4}-\d{2}-\d{2}))",
    re.MULTILINE
)

# detect which class section a deadline belongs to
CLASS_RE = re.compile(r"^## (.+)", re.MULTILINE)


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


def chat_ollama(messages: list) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": True,
        "options": {"num_ctx": 4096}
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


def find_upcoming_deadlines(school_text: str, days_ahead: int = 2, exam_days: int = 3):
    """parse SCHOOL.md and return deadlines/exams due within the window. pure date math, no LLM."""
    today = datetime.now().date()
    deadline_cutoff = today + timedelta(days=days_ahead)
    exam_cutoff = today + timedelta(days=exam_days)

    # build a map of line number -> class name
    lines = school_text.splitlines()
    class_at_line = {}
    current_class = "unknown"
    for i, line in enumerate(lines):
        m = CLASS_RE.match(line)
        if m:
            current_class = m.group(1).strip()
        class_at_line[i] = current_class

    # find all unchecked items with dates
    upcoming = []
    for match in DEADLINE_RE.finditer(school_text):
        desc = match.group(1).strip()
        date_str = match.group(2)
        try:
            due_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        # skip past deadlines
        if due_date < today:
            continue

        # figure out which class this belongs to
        line_num = school_text[:match.start()].count("\n")
        class_name = class_at_line.get(line_num, "unknown")

        is_exam = any(w in desc.lower() for w in ["exam", "midterm", "final"])
        cutoff = exam_cutoff if is_exam else deadline_cutoff

        if due_date <= cutoff:
            days_until = (due_date - today).days
            upcoming.append({
                "class": class_name,
                "description": desc,
                "date": date_str,
                "days_until": days_until,
                "is_exam": is_exam,
            })

    upcoming.sort(key=lambda x: x["days_until"])
    return upcoming


def main():
    log.session_start()

    if not SCHOOL_FILE.exists():
        print("no SCHOOL.md found, skipping.")
        log.session_end()
        return

    school = SCHOOL_FILE.read_text()
    upcoming = find_upcoming_deadlines(school)

    if not upcoming:
        print("nothing due soon. no message sent.")
        log.event("deadline_check", result="clear")
        log.session_end()
        return

    # format the items for ollama to write a natural message
    items = []
    for d in upcoming:
        days = d["days_until"]
        when = "TOMORROW" if days == 1 else f"in {days} days"
        exam = " [EXAM]" if d["is_exam"] else ""
        items.append(f"- {d['class']}: {d['description']} — due {d['date']} ({when}){exam}")
    items_text = "\n".join(items)

    prompt = f"""you are c0rtex, {USERNAME}'s ai assistant. today is {datetime.now().strftime('%A, %B %d, %Y')}.

these items are confirmed due soon (the dates are verified, do NOT change them):

{items_text}

write a short heads-up message about these deadlines. mention each item, the class, and when it's due.
write conversationally like a text message. all lowercase, no markdown, no bold, no headers, no emojis. keep it brief."""

    response = chat_ollama([{"role": "user", "content": prompt}])
    send_matrix_message(response)
    log.matrix_out(response)
    log.event("deadline_check", result="alerted", count=len(upcoming))
    print(f"deadline check sent ({len(upcoming)} items): {response[:100]}...")
    log.session_end()


if __name__ == "__main__":
    main()
