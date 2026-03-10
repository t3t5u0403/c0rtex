#!/usr/bin/env python3
"""
c0rtex_gradio — web chat interface for c0rtex

launch with: python3 scripts/c0rtex_gradio.py
access at: http://localhost:3701
"""

import gradio as gr
import json
import time
import requests
from datetime import datetime
from c0rtex_log import get_logger
from c0rtex_tools import TOOLS, execute_tool
from c0rtex_paths import CORTEX_DIR, HISTORY_FILE, SOUL_FILE, OLLAMA_HOST, USERNAME

log = get_logger("gradio")

# Load SOUL.md for personality
with open(SOUL_FILE, "r") as f:
    SOUL = f.read()

MODEL = "c0rtex"
OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"

CSS = """
.gradio-container { max-width: 860px !important; }
footer { display: none !important; }
.tool-block {
    background: #1e1e2e;
    border-left: 3px solid #ff9d00;
    padding: 8px 12px;
    margin: 6px 0;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.85em;
    color: #cdd6f4;
}
.tool-name { color: #ff9d00; font-weight: bold; }
.tool-result { color: #a6adc8; white-space: pre-wrap; }
.tool-time { color: #6c7086; font-size: 0.8em; }
"""


def format_tool_block(tool_name, result, elapsed_ms):
    """Format a tool call as a styled HTML block."""
    # Truncate long results for display
    display_result = result[:500] + "..." if len(result) > 500 else result
    display_result = display_result.replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<div class="tool-block">'
        f'<span class="tool-name">[tool: {tool_name}]</span> '
        f'<span class="tool-time">({elapsed_ms}ms)</span><br>'
        f'<span class="tool-result">{display_result}</span>'
        f'</div>'
    )


def chat_with_c0rtex(message, history):
    """
    Streaming chat handler. Yields partial text as it arrives from Ollama.
    """

    # Build messages for Ollama
    messages = [{"role": "system", "content": SOUL}]

    # Add history (Gradio 4+ passes list of {"role": ..., "content": ...} dicts)
    # Content may be a string or a list like [{"text": "...", "type": "text"}]
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
        if content:
            messages.append({"role": role, "content": content})

    # Add current message
    messages.append({"role": "user", "content": message})

    log.event("chat_request", message=message)

    # First request — non-streaming to check for tool calls
    try:
        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "tools": TOOLS,
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if not tool_calls:
            # No tool calls — re-request with streaming
            payload["stream"] = True
            del payload["tools"]
            payload["messages"] = messages

            response = requests.post(OLLAMA_URL, json=payload, timeout=300, stream=True)
            response.raise_for_status()

            partial = ""
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    partial += token
                    yield partial
                if chunk.get("done"):
                    break

            log.event("chat_response", response_length=len(partial))
            return

        # Handle tool calls
        tool_output = ""
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name")
            tool_args = tool_call.get("function", {}).get("arguments", {})

            log.event("tool_call", tool_name=tool_name, tool_args=tool_args)

            # Show tool running status
            tool_output += f'<div class="tool-block"><span class="tool-name">[tool: {tool_name}]</span> running...</div>\n'
            yield tool_output

            t0 = time.time()
            try:
                result = execute_tool(tool_name, tool_args)
            except Exception as te:
                result = f"error: {te}"
            elapsed = int((time.time() - t0) * 1000)

            log.event("tool_result", tool_name=tool_name, elapsed_ms=elapsed)

            # Replace "running..." with actual result
            tool_output = tool_output.replace(
                f'<span class="tool-name">[tool: {tool_name}]</span> running...</div>',
                f'{format_tool_block(tool_name, result, elapsed)[len("<div class="):]}'
            )

            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            messages.append({"role": "tool", "content": result})

        yield tool_output + "\n\n"

        # Stream the final response after tool results
        try:
            follow_up = {
                "model": MODEL,
                "messages": messages,
                "stream": True,
            }
            response = requests.post(OLLAMA_URL, json=follow_up, timeout=300, stream=True)
            response.raise_for_status()

            partial = tool_output + "\n\n"
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    partial += token
                    yield partial
                if chunk.get("done"):
                    break

            log.event("chat_response", response_length=len(partial))

        except Exception as e:
            yield tool_output + f"\n\ntimed out generating response after tool calls: {e}"

    except Exception as e:
        log.error("chat_error", str(e))
        yield f"error: {e}"


# Create Gradio interface
with gr.Blocks(title="c0rtex") as demo:
    gr.Markdown("# c0rtex\nprivacy-first ai assistant running locally")
    gr.ChatInterface(fn=chat_with_c0rtex)
    gr.Markdown(
        f"<center style='color:#6c7086; font-size:0.8em;'>"
        f"chatting as: {USERNAME} &nbsp;|&nbsp; model: {MODEL} &nbsp;|&nbsp; {OLLAMA_HOST}"
        f"</center>"
    )

if __name__ == "__main__":
    print("Starting c0rtex web interface...")
    print(f"Open http://localhost:3701 in your browser")
    demo.launch(
        server_name="0.0.0.0",
        server_port=3701,
        share=False,  # Set to True to create public link
        css=CSS,
    )
