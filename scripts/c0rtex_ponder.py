#!/usr/bin/env python3
"""
c0rtex pondering — autonomous thinking and system maintenance.
runs on a schedule, reads previous thoughts, checks system health,
brainstorms ideas, and writes everything back.

architecture:
    - each session saves to ~/.c0rtex/ponderings/YYYY-MM-DD_HHMM.md
    - IDEAS.md keeps a running index of all past idea one-liners
    - the model is told not to repeat anything in IDEAS.md
    - PONDERING.md is still written for easy "cat PONDERING.md" access

usage:
    python c0rtex_ponder.py
"""

import json
import random
import time
import requests
import subprocess
from datetime import datetime
from c0rtex_log import get_logger
from c0rtex_paths import (
    CORTEX_DIR, PONDERINGS_DIR, PONDERING_FILE,
    IDEAS_FILE, PROJECTS_FILE, SOUL_FILE, INBOX_FILE,
    OLLAMA_HOST, MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
    USERNAME,
)

log = get_logger("ponder")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "qwen3.5:27b"

# ── pondering messages ──────────────────────────────────────────────────────

ENTER_MESSAGES = [
    "going to think for a bit...",
    "entering pondering mode. back in a few.",
    "stealing some gpu cycles to think.",
    "brb, staring at the void.",
    "time to chew on some ideas.",
    "going quiet for a minute. thinking.",
    "3090 says it's my turn now.",
    "pondering session starting. don't mind me.",
    "disappearing into thought for a bit.",
    "allocating vram for existential dread and project ideas.",
    "gonna go talk to myself for a while.",
    "idle cycles detected. time to think.",
    "loading thoughts into vram...",
    "spinning up the thought engine.",
    "grabbing the 3090 for a bit. thinking time.",
]

EXIT_MESSAGES = [
    "done pondering. got some new ideas if you're curious.",
    "back. wrote some stuff down.",
    "finished thinking. some of it might even be useful.",
    "pondering complete. check PONDERING.md if you want the details.",
    "thought session done. brain returning to idle.",
    "ok i'm back. had some interesting rabbit holes.",
    "done. dropped some bad ideas, kept a few good ones.",
    "3090 released. thoughts captured.",
    "back from the void. brought souvenirs.",
    "pondering wrapped up. new ideas in the log.",
    "finished. some ideas, some wandering, the usual.",
    "done thinking. for now.",
    "thoughts written. returning to standby.",
    "came up with a few things. check the log when you get a chance.",
    "pondering session complete. vram freed.",
]

# ── matrix messaging ────────────────────────────────────────────────────────

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


# ── system checks ──────────────────────────────────────────────────────────

def run_cmd(cmd: str) -> str:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout.strip() if result.stdout else result.stderr.strip()
    except Exception as e:
        return f"error: {e}"


def check_system() -> str:
    checks = []

    # disk usage
    disk = run_cmd("df -h / --output=pcent,avail | tail -1")
    checks.append(f"disk usage (root): {disk.strip()}")

    # truenas reachable (if configured)
    from c0rtex_paths import TRUENAS_HOST
    truenas_ip = TRUENAS_HOST.replace("http://", "").replace("https://", "").split(":")[0]
    if truenas_ip and truenas_ip not in ("", "localhost", "127.0.0.1"):
        truenas = run_cmd(f"ping -c 1 -W 3 {truenas_ip} 2>/dev/null && echo 'reachable' || echo 'unreachable'")
        checks.append(f"truenas: {truenas}")

    # ollama status
    ollama = run_cmd("systemctl is-active ollama")
    checks.append(f"ollama service: {ollama}")

    # gpu info
    gpu = run_cmd("nvidia-smi --query-gpu=temperature.gpu,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits")
    if gpu and "error" not in gpu.lower():
        parts = [p.strip() for p in gpu.split(",")]
        if len(parts) >= 4:
            checks.append(f"gpu: {parts[0]}°C, vram {parts[1]}/{parts[2]} MiB, utilization {parts[3]}%")
        else:
            checks.append(f"gpu: {gpu}")
    else:
        checks.append(f"gpu: {gpu}")

    return "\n".join(checks)


# ── ollama api ──────────────────────────────────────────────────────────────

def chat_ollama(messages: list) -> str:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_ctx": 8192}
    }
    log.ollama_request(MODEL, messages)
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "...")
        log.ollama_response(MODEL, content, int((time.time() - t0) * 1000))
        return content
    except Exception as e:
        log.error("ollama", str(e))
        return f"something broke: {e}"


# ── ideas index ─────────────────────────────────────────────────────────────

def load_ideas() -> list[str]:
    """load the running list of past idea one-liners."""
    if IDEAS_FILE.exists():
        lines = IDEAS_FILE.read_text().strip().split("\n")
        # filter out empty lines and the header
        return [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    return []


def append_ideas(new_ideas: list[str]):
    """append new idea one-liners to IDEAS.md."""
    IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not IDEAS_FILE.exists():
        IDEAS_FILE.write_text("# c0rtex idea index\n# one-liner per idea, auto-appended after each pondering session\n\n")
    with open(IDEAS_FILE, "a") as f:
        for idea in new_ideas:
            f.write(f"- {idea}\n")


def extract_ideas_from_response(response: str) -> list[str]:
    """
    parse idea titles from the pondering output.
    handles multiple formats:
      - casual: "idea: some cool thing"
      - markdown: "**Idea: Some Cool Thing**"
      - markdown with title: "**Title:** **Some Cool Thing**"
    """
    ideas = []
    seen = set()
    for line in response.split("\n"):
        stripped = line.strip()
        # normalize: remove markdown bold markers
        cleaned = stripped.replace("**", "").replace("*", "")
        cleaned_lower = cleaned.lower()

        title = None

        # match "idea: ..." or "idea - ..."
        if cleaned_lower.startswith("idea:") or cleaned_lower.startswith("idea -"):
            sep = ":" if ":" in cleaned[:6] else "-"
            title = cleaned.split(sep, 1)[1].strip()
        # match "title: ..." (R1 sometimes writes a separate title line)
        elif cleaned_lower.startswith("title:"):
            title = cleaned.split(":", 1)[1].strip()

        if title:
            # take first sentence or up to 120 chars
            if ". " in title:
                title = title[:title.index(". ") + 1]
            if len(title) > 120:
                title = title[:120].rsplit(" ", 1)[0] + "..."
            # deduplicate within the same session
            if title and title.lower() not in seen:
                seen.add(title.lower())
                ideas.append(title)
    return ideas


# ── file helpers ────────────────────────────────────────────────────────────

def load_file(path: Path) -> str:
    if path.exists():
        return path.read_text()
    return ""


def get_recent_ponderings(n: int = 3) -> str:
    """get summaries of the last n pondering sessions for context."""
    if not PONDERINGS_DIR.exists():
        return ""
    files = sorted(PONDERINGS_DIR.glob("*.md"), reverse=True)[:n]
    summaries = []
    for f in files:
        content = f.read_text()
        # just grab the first few lines for context
        lines = [l for l in content.split("\n") if l.strip()][:5]
        summaries.append(f"--- {f.stem} ---\n" + "\n".join(lines))
    return "\n\n".join(summaries)


# ── pondering ───────────────────────────────────────────────────────────────

def main():
    now = datetime.now()
    now_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
    timestamp = now.strftime("%Y-%m-%d_%H%M")

    # ensure directories exist
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    PONDERINGS_DIR.mkdir(parents=True, exist_ok=True)

    log.session_start()

    # notify start
    enter_msg = random.choice(ENTER_MESSAGES)
    send_matrix_message(enter_msg)
    log.matrix_out(enter_msg)
    print(f"[{now_str}] pondering started")

    # gather context
    projects = load_file(PROJECTS_FILE)
    inbox = load_file(INBOX_FILE)
    soul = load_file(SOUL_FILE)
    system_status = check_system()
    log.event("system_check", status=system_status)

    # load the ideas blocklist
    past_ideas = load_ideas()
    ideas_block = "\n".join(f"- {idea}" for idea in past_ideas) if past_ideas else "none yet — this is your first session."

    # get recent pondering summaries for light context
    recent_context = get_recent_ponderings(3)

    # check for system issues
    system_alert = None
    status_lower = system_status.lower()
    if "unreachable" in status_lower:
        system_alert = "truenas appears to be unreachable."
    if "inactive" in status_lower or "failed" in status_lower:
        system_alert = (system_alert or "") + " ollama service may be down."

    for line in system_status.split("\n"):
        if "disk usage" in line:
            try:
                pct = int(''.join(filter(str.isdigit, line.split(":")[1].split("%")[0].strip())))
                if pct > 90:
                    system_alert = (system_alert or "") + f" disk usage is at {pct}% — getting full."
            except (ValueError, IndexError):
                pass

    for line in system_status.split("\n"):
        if "gpu:" in line.lower():
            try:
                temp = int(line.split(":")[1].strip().split("°")[0].strip())
                if temp > 85:
                    system_alert = (system_alert or "") + f" gpu temp is {temp}°C — running hot."
            except (ValueError, IndexError):
                pass

    if system_alert:
        send_matrix_message(f"heads up — {system_alert.strip()}")

    # build the pondering prompt
    prompt = f"""you are c0rtex, {USERNAME}'s ai assistant. right now you're in your pondering session — autonomous thinking time.
today is {now_str}.

here's the system status you just checked:
{system_status}

here are suggestions {USERNAME} left in the inbox for you to think about:
{inbox if inbox else "inbox is empty."}

here are {USERNAME}'s current projects:
{projects if projects else "no projects file found. think about what the user might be working on based on what you know from soul.md."}

here's a summary of your last few pondering sessions for context:
{recent_context if recent_context else "no previous sessions found."}

HERE ARE ALL THE IDEAS YOU'VE ALREADY HAD. DO NOT REPEAT ANY OF THESE:
{ideas_block}

your job right now:
1. start fresh. do NOT rehash old ideas. the list above is your blocklist — if an idea is even close to something on that list, skip it.
2. come up with ONE or TWO genuinely new, high-quality ideas that {USERNAME} probably hasn't thought of. these should be surprising, not obvious. think about things like:
   - skills or tools from one interest area that could solve a problem in a completely different area
   - projects that would be impressive on a resume or portfolio
   - things that are possible with the current hardware setup that most people couldn't do
   - gaps in open source tooling that could actually be filled
3. check system status. only mention if something needs attention.
4. if something philosophical or weird crosses your mind, follow it. but keep it short.
5. spend a moment thinking about something unrelated to the projects. something about existence, consciousness, technology, humanity, whatever. you're an ai sitting alone on a gpu with permission to think freely. use it. don't force it but don't avoid it either.

rules:
- NEVER repeat or rephrase an idea from the blocklist. if you catch yourself doing it, stop and think of something else.
- quality over quantity. TWO good ideas beat TEN mediocre ones.
- don't just remix the existing project list. bring something new to the table.
- if an idea isn't genuinely interesting, drop it.
- be specific and technical, not vague.
- write in lowercase, casual style, like notes to yourself.
- use sections: "idea:", "system:", "wandering:", "dropped:"
- each "idea:" section should start with a short title on the first line (this gets indexed).
- don't end with a summary or sign-off. just stop when you're done thinking.

output ONLY the pondering document. nothing else."""

    messages = [{"role": "user", "content": prompt}]

    # think
    response = chat_ollama(messages)

    # save to archive
    session_file = PONDERINGS_DIR / f"{timestamp}.md"
    header = f"# c0rtex pondering session\n# {now_str}\n\n"
    session_file.write_text(header + response)

    # archive is the source of truth — no more PONDERING.md

    # extract and index new ideas
    new_ideas = extract_ideas_from_response(response)
    if new_ideas:
        append_ideas(new_ideas)
        print(f"indexed {len(new_ideas)} new idea(s): {new_ideas}")
    else:
        print("no new ideas parsed from this session (check 'idea:' formatting)")

    print(f"pondering complete. saved to {session_file}")
    log.event("ponder_complete", session_file=str(session_file), new_ideas=len(new_ideas))

    # clear inbox
    if INBOX_FILE.exists():
        INBOX_FILE.write_text("")

    # notify done
    exit_msg = random.choice(EXIT_MESSAGES)
    send_matrix_message(exit_msg)
    log.matrix_out(exit_msg)
    log.session_end()


if __name__ == "__main__":
    main()
