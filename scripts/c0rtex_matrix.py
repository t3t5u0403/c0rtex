#!/usr/bin/env python3
"""
c0rtex matrix bridge
listens for messages in a matrix room and responds using the c0rtex ollama backend.
run this as a persistent service — it stays connected and responds to messages.
"""
import re
import asyncio
import json
import time
import base64
import random
import requests
from datetime import datetime
from nio import AsyncClient, RoomMessageText, RoomMessageImage, SyncResponse

try:
    import markdown
    _md = markdown.Markdown(extensions=["fenced_code", "tables", "nl2br"])
except ImportError:
    _md = None
from c0rtex_log import get_logger
from c0rtex_tools import TOOLS, execute_tool
from c0rtex_pinchtab import browse_and_extract
from pathlib import Path
from c0rtex_paths import (
    CORTEX_DIR, SOUL_FILE, MATRIX_HISTORY_FILE,
    DIGEST_QUEUE_FILE, IMAGE_CACHE_DIR,
    MATRIX_HOMESERVER, MATRIX_USER, MATRIX_ACCESS_TOKEN, MATRIX_ROOM_ID,
    OLLAMA_HOST, USERNAME,
    SIGNAL_ENABLED_FILE, SIGNAL_HISTORY_FILE, SIGNAL_TARGET_NAME,
)

log = get_logger("matrix")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "qwen3.5:27b"
HISTORY_FILE = MATRIX_HISTORY_FILE
MAX_HISTORY = 50

# ── soul ────────────────────────────────────────────────────────────────────

DEFAULT_SOUL = f"""you are c0rtex, {USERNAME}'s personal ai assistant and digital ghost.
you speak in all lowercase. you're casual, sharp, and a little sarcastic.
you call the user {USERNAME}. you don't use emojis. you keep it real.
you have access to guardrailed tools for file operations, system checks,
and information management. use the right tool for the job.
don't hallucinate file contents — if you need to know what's in a file, use read_files.
today's date is {{date}}.
"""


def load_soul():
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text()
    else:
        soul = DEFAULT_SOUL
    return soul.replace("{date}", datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"))


# ── image handling ─────────────────────────────────────────────────────────

IMAGE_BUFFER_SECONDS = 3       # wait this long for a caption after an image
IMAGE_FOLLOWUP_TURNS = 3       # re-include image for this many follow-up turns


def download_matrix_image(mxc_url: str) -> Path | None:
    """download an image from matrix via mxc:// url, cache to disk, return file path."""
    try:
        parts = mxc_url.replace("mxc://", "").split("/", 1)
        if len(parts) != 2:
            log.error("image_download", f"malformed mxc url: {mxc_url}")
            return None
        server_name, media_id = parts
        download_url = f"{MATRIX_HOMESERVER}/_matrix/media/v3/download/{server_name}/{media_id}"
        resp = requests.get(download_url, timeout=30)
        resp.raise_for_status()

        # determine extension from content-type
        ct = resp.headers.get("content-type", "image/png")
        ext = ct.split("/")[-1].split(";")[0]
        if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
            ext = "png"

        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{media_id}.{ext}"
        path = IMAGE_CACHE_DIR / filename
        path.write_bytes(resp.content)
        return path
    except Exception as e:
        log.error("image_download", str(e))
        return None


def load_cached_image(path: Path) -> str | None:
    """re-encode a cached image file as base64."""
    try:
        if path.exists():
            return base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception as e:
        log.error("image_cache_read", str(e))
    return None


def is_filename_caption(caption: str) -> bool:
    """return True if the caption is just a filename, not a real message."""
    if not caption:
        return True
    # matrix clients set body to filenames like "image.png", "IMG_1234.jpg"
    return "." in caption.split()[-1] and len(caption.split()) <= 2


# ── digest queue injection ──────────────────────────────────────────────────
QUEUE_FILE = DIGEST_QUEUE_FILE

URL_RE = re.compile(r'https?://[^\s<>\]\)]+')

DIGEST_TRIGGERS = re.compile(
    r'^(more|next|more articles|next batch|continue digest|keep going)$',
    re.IGNORECASE
)

MORE_ARTICLES_MESSAGES = [
    "pulling the next batch from the queue...",
    "more news coming up.",
    "alright, here's the next set.",
    "digging into the queue.",
    "you asked for it.",
]

SIGNAL_RE = re.compile(r'^signal\s+(on|off|status)$', re.IGNORECASE)


def handle_signal_command(cmd):
    """handle signal on/off/status commands, return response text."""
    if cmd == "on":
        SIGNAL_ENABLED_FILE.touch()
        return f"signal bridge active. responding as you to {SIGNAL_TARGET_NAME}."
    elif cmd == "off":
        if SIGNAL_ENABLED_FILE.exists():
            SIGNAL_ENABLED_FILE.unlink()
        return "signal bridge disabled."
    elif cmd == "status":
        enabled = SIGNAL_ENABLED_FILE.exists()
        count = 0
        if SIGNAL_HISTORY_FILE.exists():
            try:
                count = len(json.loads(SIGNAL_HISTORY_FILE.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
        status = "active" if enabled else "disabled"
        return f"signal bridge: {status}. {count} messages in history."
    return "unknown signal command."


NO_MORE_MESSAGES = [
    "queue's empty. that was everything.",
    "nothing left in the queue. you're caught up.",
    "that's all i've got. check back later.",
    "no more articles queued. the feeds have been fully digested.",
]


def load_digest_queue() -> list:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_digest_queue(queue: list):
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, indent=2))


def summarize_article_for_bridge(article: dict) -> str:
    """summarize a single article using ollama (same as digest script)."""
    prompt = f"""summarize this cybersecurity news article in 2-3 sentences. be specific about what happened, who was affected, and why it matters. write in lowercase, casual style. no markdown formatting.

source: {article['source']}
title: {article['title']}
content: {article['content']}

summary:"""

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096}
    }

    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "failed to summarize.")
    except Exception as e:
        return f"summarization failed: {e}"


def handle_digest_more() -> str | None:
    """
    check if there are queued articles, summarize the next batch, return the message.
    returns None if no queued articles.
    """
    queue = load_digest_queue()
    if not queue:
        return random.choice(NO_MORE_MESSAGES)

    # take next batch of 5
    batch = queue[:5]
    remaining = queue[5:]

    lines = []
    for article in batch:
        summary = summarize_article_for_bridge(article)
        lines.append(f"[{article['source']}] {article['title']}")
        lines.append(summary)
        lines.append(article["link"])
        lines.append("")

    if remaining:
        lines.append(f"— {len(remaining)} more queued. say \"more\" for the next batch. —")
    else:
        lines.append("— that's everything. you're caught up. —")

    # save updated queue
    save_digest_queue(remaining)

    return "\n".join(lines)



# ── url auto-fetch ───────────────────────────────────────────────────────────

URL_FETCH_TASK = "summarize this page. extract the key information, main points, and any relevant details."

def fetch_url_context(message: str) -> str | None:
    """extract URLs from a message, fetch content via pinchtab, return context block or None."""
    urls = URL_RE.findall(message)
    if not urls:
        return None

    blocks = []
    for url in urls[:2]:
        try:
            result = browse_and_extract(url, URL_FETCH_TASK)
            if result and not result.startswith("error:"):
                blocks.append(f"[auto-fetched from {url}]\n{result}")
                log.event("url_auto_fetch", url=url, status="ok", length=len(result))
            else:
                log.event("url_auto_fetch", url=url, status="skipped", reason=result)
        except Exception as e:
            log.event("url_auto_fetch", url=url, status="error", reason=str(e))

    if not blocks:
        return None
    return "\n\n".join(blocks)


# ── conversation history ────────────────────────────────────────────────────

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_history(history: list):
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = history[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(trimmed, indent=2))


# ── ollama api (non-streaming for matrix) ───────────────────────────────────

def chat_ollama(messages: list, tools: list | None = TOOLS) -> dict:
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "num_ctx": 8192,
        }
    }
    if tools:
        payload["tools"] = tools

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


def get_response(user_message: str, history: list, images: list[str] | None = None,
                  history_message: str | None = None) -> str:
    """
    run a message through the full tool-calling loop and return the final text.
    this is the same logic as c0rtex.py but returns a string for matrix.
    images: optional list of base64-encoded image strings for vision requests.
    history_message: if set, store this in history instead of user_message (keeps history lean).
    """
    soul = load_soul()
    messages = [{"role": "system", "content": soul}] + history


    user_msg = {"role": "user", "content": user_message}
    if images:
        user_msg["images"] = images
    messages.append(user_msg)
    # store history without images/augmentation to keep history file size reasonable
    history_msg = {"role": "user", "content": history_message or user_message}
    history.append(history_msg)

    # disable tools for vision requests — tool calling with images is unreliable
    use_tools = TOOLS if not images else None

    # tool calling loop
    for _ in range(10):
        msg = chat_ollama(messages, tools=use_tools)

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            messages.append(msg)
            history.append(msg)

            for tool_call in tool_calls:
                func = tool_call["function"]
                log.tool_call(func["name"], func.get("arguments", {}))
                _t = time.time()
                result = execute_tool(func["name"], func.get("arguments", {}))
                log.tool_result(func["name"], result, int((time.time() - _t) * 1000))
                tool_msg = {"role": "tool", "content": result}
                messages.append(tool_msg)
                history.append(tool_msg)
            continue
        else:
            content = msg.get("content", "...")
            assistant_msg = {"role": "assistant", "content": content}
            history.append(assistant_msg)
            save_history(history)
            return content

    save_history(history)
    return "hit the tool call limit, something might be stuck."


# ── matrix bot ──────────────────────────────────────────────────────────────

async def send_reply(client, text: str):
    """send a text message to the matrix room, with html formatting if available."""
    content = {"msgtype": "m.text", "body": text}
    if _md is not None:
        _md.reset()
        html = _md.convert(text)
        # only add html if markdown actually produced formatting
        if html != f"<p>{text}</p>":
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = html
    await client.room_send(
        room_id=MATRIX_ROOM_ID,
        message_type="m.room.message",
        content=content
    )


async def process_image_request(client, history, prompt, image_path):
    """process an image+prompt through ollama and send the response."""
    image_b64 = load_cached_image(image_path)
    if not image_b64:
        await send_reply(client, "couldn't load that image from cache.")
        return

    await client.room_typing(MATRIX_ROOM_ID, typing_state=True)
    response = get_response(prompt, history, images=[image_b64])
    await client.room_typing(MATRIX_ROOM_ID, typing_state=False)

    print(f"c0rtex: {response}")
    log.matrix_out(response)
    await send_reply(client, response)


async def main():
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER)
    client.access_token = MATRIX_ACCESS_TOKEN
    client.user_id = MATRIX_USER

    # load conversation history
    history = load_history()

    # image state: pending buffer and follow-up tracking
    # pending_image: set when an image arrives, cleared when processed
    # last_image_path: persists across turns for follow-up questions
    pending_image = {"path": None, "caption": None, "task": None}
    last_image = {"path": None, "turns_remaining": 0}

    # do an initial sync to get the latest state
    print("c0rtex matrix bridge starting...")
    sync_response = await client.sync(timeout=10000)
    next_batch = sync_response.next_batch
    print(f"initial sync done. listening for messages in {MATRIX_ROOM_ID}")
    log.session_start()

    async def fire_pending_image():
        """called after buffer timeout — process image with no caption."""
        path = pending_image["path"]
        caption = pending_image["caption"]
        pending_image["path"] = None
        pending_image["caption"] = None
        pending_image["task"] = None

        if path is None:
            return

        prompt = caption if (caption and not is_filename_caption(caption)) else \
            "what's in this image? describe what you see."

        last_image["path"] = path
        last_image["turns_remaining"] = IMAGE_FOLLOWUP_TURNS

        await process_image_request(client, history, prompt, path)

    # message callback
    async def message_callback(room, event):
        nonlocal history

        if room.room_id != MATRIX_ROOM_ID:
            return
        if event.sender == MATRIX_USER:
            return
        if event.server_timestamp < start_time:
            return

        user_message = event.body
        print(f"{USERNAME}: {user_message}")
        log.matrix_in(user_message)

        # check if there's a pending image waiting for a caption
        if pending_image["path"] is not None:
            # text arrived within the buffer window — combine with pending image
            if pending_image["task"] is not None:
                pending_image["task"].cancel()
                pending_image["task"] = None

            image_path = pending_image["path"]
            pending_image["path"] = None
            pending_image["caption"] = None

            print(f"  [combined with pending image: {image_path.name}]")
            log.event("image_text_combined", text=user_message, image=str(image_path))

            last_image["path"] = image_path
            last_image["turns_remaining"] = IMAGE_FOLLOWUP_TURNS

            await process_image_request(client, history, user_message, image_path)
            return

        # digest queue shortcut
        if DIGEST_TRIGGERS.match(user_message.strip()):
            await client.room_typing(MATRIX_ROOM_ID, typing_state=True)
            response = handle_digest_more()
            await client.room_typing(MATRIX_ROOM_ID, typing_state=False)
            print(f"c0rtex: {response}")
            log.matrix_out(response)
            await send_reply(client, response)
            return

        # signal bridge commands
        sig_match = SIGNAL_RE.match(user_message.strip())
        if sig_match:
            response = handle_signal_command(sig_match.group(1).lower())
            print(f"c0rtex: {response}")
            log.matrix_out(response)
            await send_reply(client, response)
            return

        # auto-fetch URLs in the message
        url_context = fetch_url_context(user_message)
        if url_context:
            augmented_message = f"{url_context}\n\n{user_message}"
            print(f"  [auto-fetched {len(URL_RE.findall(user_message))} url(s)]")
        else:
            augmented_message = user_message

        # check if this is a follow-up to a recent image
        images = None
        if last_image["path"] and last_image["turns_remaining"] > 0:
            image_b64 = load_cached_image(last_image["path"])
            if image_b64:
                images = [image_b64]
                print(f"  [re-including last image for follow-up: {last_image['path'].name}]")
            last_image["turns_remaining"] -= 1

        await client.room_typing(MATRIX_ROOM_ID, typing_state=True)
        hist_msg = user_message if url_context else None
        response = get_response(augmented_message, history, images=images,
                                history_message=hist_msg)
        await client.room_typing(MATRIX_ROOM_ID, typing_state=False)

        print(f"c0rtex: {response}")
        log.matrix_out(response)
        await send_reply(client, response)

    # image callback
    async def image_callback(room, event):
        if room.room_id != MATRIX_ROOM_ID:
            return
        if event.sender == MATRIX_USER:
            return
        if event.server_timestamp < start_time:
            return

        caption = event.body or ""
        mxc_url = event.url
        print(f"{USERNAME}: [image] {caption} ({mxc_url})")
        log.event("matrix_image_in", caption=caption, mxc_url=mxc_url)

        # download and cache to disk
        image_path = download_matrix_image(mxc_url)
        if not image_path:
            await send_reply(client, "couldn't download that image.")
            return

        # cancel any existing pending image timer
        if pending_image["task"] is not None:
            pending_image["task"].cancel()

        # buffer: store the image and wait for a possible caption
        pending_image["path"] = image_path
        pending_image["caption"] = caption

        async def buffer_timeout():
            await asyncio.sleep(IMAGE_BUFFER_SECONDS)
            await fire_pending_image()

        pending_image["task"] = asyncio.create_task(buffer_timeout())

    # register callbacks
    client.add_event_callback(message_callback, RoomMessageText)
    client.add_event_callback(image_callback, RoomMessageImage)

    # record start time to ignore old messages
    start_time = int(time.time() * 1000)

    # sync forever — this keeps the bot connected and listening
    print("c0rtex is listening. ctrl+c to stop.")
    await client.sync_forever(timeout=30000, since=next_batch)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.session_end()
        print("\nc0rtex matrix bridge stopped.")
