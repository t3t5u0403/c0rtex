#!/usr/bin/env python3
"""
c0rtex — local ai assistant
a lightweight python wrapper around ollama with tool calling.
"""

import json
import time
import requests
import sys
from datetime import datetime
from c0rtex_log import get_logger
from c0rtex_tools import TOOLS, execute_tool
from c0rtex_paths import CORTEX_DIR, HISTORY_FILE, SOUL_FILE, OLLAMA_HOST, USERNAME, ensure_directories

log = get_logger("c0rtex")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "c0rtex"  # your ollama modelfile
MAX_HISTORY = 50  # keep last N messages to avoid blowing context

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
    """load personality from SOUL.md if it exists, otherwise use default."""
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text()
    else:
        soul = DEFAULT_SOUL
    return soul.replace("{date}", datetime.now().strftime("%A, %B %d, %Y"))


# ── conversation history ────────────────────────────────────────────────────

def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_history(messages: list):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    trimmed = messages[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(trimmed, indent=2))


# ── ollama api ──────────────────────────────────────────────────────────────

def chat_stream(messages: list, use_tools: bool = True):
    """
    stream a response from ollama.
    text gets printed token by token as it arrives.
    tool calls get collected and returned for execution.
    returns the full assembled message when done.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": 8192,
        }
    }
    if use_tools:
        payload["tools"] = TOOLS

    log.ollama_request(MODEL, messages, stream=True, tools=use_tools)
    t0 = time.time()

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=120,
            stream=True
        )
        resp.raise_for_status()

        full_content = ""
        full_tool_calls = []

        for line in resp.iter_lines():
            if not line:
                continue

            chunk = json.loads(line)
            msg = chunk.get("message", {})

            # collect tool calls
            if msg.get("tool_calls"):
                full_tool_calls.extend(msg["tool_calls"])

            # stream text to terminal as it arrives
            token = msg.get("content", "")
            if token:
                full_content += token
                print(token, end="", flush=True)

            # done — return full message
            if chunk.get("done"):
                if full_content:
                    print()  # newline after streamed text
                tc_names = [tc["function"]["name"] for tc in full_tool_calls] if full_tool_calls else []
                log.ollama_response(MODEL, full_content, int((time.time() - t0) * 1000),
                                    tool_call_names=tc_names)
                return {
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": full_tool_calls if full_tool_calls else None
                }

        log.ollama_response(MODEL, full_content or "...", int((time.time() - t0) * 1000))
        return {
            "role": "assistant",
            "content": full_content or "...",
            "tool_calls": full_tool_calls if full_tool_calls else None
        }

    except requests.exceptions.Timeout:
        log.error("timeout", "ollama timed out")
        print("timed out on that one. try again?")
        return {"role": "assistant", "content": "timed out on that one. try again?"}
    except requests.exceptions.ConnectionError:
        log.error("connection", "cannot reach ollama")
        print("can't reach ollama. is it running?")
        return {"role": "assistant", "content": "can't reach ollama. is it running?"}
    except Exception as e:
        log.error("unknown", str(e))
        print(f"something broke: {e}")
        return {"role": "assistant", "content": f"something broke: {e}"}


def chat_no_stream(messages: list, use_tools: bool = True) -> dict:
    """non-streaming version for single-shot / cron mode."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": 8192,
        }
    }
    if use_tools:
        payload["tools"] = TOOLS

    log.ollama_request(MODEL, messages, tools=use_tools)
    t0 = time.time()

    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        tc_names = [tc["function"]["name"] for tc in (msg.get("tool_calls") or [])]
        log.ollama_response(MODEL, msg.get("content", ""), int((time.time() - t0) * 1000),
                            tool_call_names=tc_names)
        return msg
    except requests.exceptions.Timeout:
        log.error("timeout", "ollama timed out")
        return {"role": "assistant", "content": "timed out on that one. try again?"}
    except requests.exceptions.ConnectionError:
        log.error("connection", "cannot reach ollama")
        return {"role": "assistant", "content": "can't reach ollama. is it running?"}
    except Exception as e:
        log.error("unknown", str(e))
        return {"role": "assistant", "content": f"something broke: {e}"}


# ── main loop ───────────────────────────────────────────────────────────────

def conversation_loop():
    """the core loop. send message → handle tool calls → stream response."""
    soul = load_soul()
    history = load_history()

    messages = [{"role": "system", "content": soul}] + history

    print("c0rtex online. type 'exit' to quit, 'clear' to reset history.\n")

    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nlater.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("later.")
            break
        if user_input.lower() == "clear":
            history.clear()
            messages = [{"role": "system", "content": soul}]
            save_history(history)
            print("history cleared.\n")
            continue

        # add user message
        user_msg = {"role": "user", "content": user_input}
        messages.append(user_msg)
        history.append(user_msg)

        # tool calling loop
        max_tool_rounds = 10
        for _ in range(max_tool_rounds):
            print()  # blank line before response
            msg = chat_stream(messages)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # save assistant message with tool calls to history
                history_msg = {"role": "assistant", "content": msg.get("content", "")}
                history_msg["tool_calls"] = tool_calls
                messages.append(history_msg)
                history.append(history_msg)

                # execute each tool
                for tool_call in tool_calls:
                    func = tool_call["function"]
                    tool_name = func["name"]
                    tool_args = func.get("arguments", {})

                    print(f"  [tool: {tool_name}]")
                    log.tool_call(tool_name, tool_args)
                    _t = time.time()
                    result = execute_tool(tool_name, tool_args)
                    log.tool_result(tool_name, result, int((time.time() - _t) * 1000))

                    tool_msg = {"role": "tool", "content": result}
                    messages.append(tool_msg)
                    history.append(tool_msg)

                continue
            else:
                # text response already printed by stream
                content = msg.get("content", "...")
                assistant_msg = {"role": "assistant", "content": content}
                messages.append(assistant_msg)
                history.append(assistant_msg)
                print()  # blank line after response
                break

        save_history(history)


# ── cli entry point ─────────────────────────────────────────────────────────

def main():
    ensure_directories()
    log.session_start()
    try:
        if len(sys.argv) > 1:
            # single-shot mode for cron jobs / scripts
            # usage: python c0rtex.py "give me my morning briefing"
            prompt = " ".join(sys.argv[1:])
            soul = load_soul()
            messages = [
                {"role": "system", "content": soul},
                {"role": "user", "content": prompt}
            ]

            for _ in range(10):
                msg = chat_no_stream(messages)
                tool_calls = msg.get("tool_calls")

                if tool_calls:
                    messages.append(msg)
                    for tool_call in tool_calls:
                        func = tool_call["function"]
                        log.tool_call(func["name"], func.get("arguments", {}))
                        _t = time.time()
                        result = execute_tool(func["name"], func.get("arguments", {}))
                        log.tool_result(func["name"], result, int((time.time() - _t) * 1000))
                        messages.append({"role": "tool", "content": result})
                    continue
                else:
                    print(msg.get("content", "..."))
                    break
        else:
            conversation_loop()
    finally:
        log.session_end()


if __name__ == "__main__":
    main()
