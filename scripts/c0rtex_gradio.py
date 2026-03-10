#!/usr/bin/env python3
"""
c0rtex_gradio — web chat interface for c0rtex

launch with: python3 scripts/c0rtex_gradio.py
access at: http://localhost:3701
"""

import gradio as gr
import json
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


def chat_with_c0rtex(message, history):
    """
    Main chat handler. Takes user message and chat history,
    returns c0rtex's response.

    history format: [[user_msg, bot_msg], [user_msg, bot_msg], ...]
    """

    # Build messages for Ollama
    messages = [{"role": "system", "content": SOUL}]

    # Add history
    for user_msg, bot_msg in history:
        messages.append({"role": "user", "content": user_msg})
        if bot_msg:
            messages.append({"role": "assistant", "content": bot_msg})

    # Add current message
    messages.append({"role": "user", "content": message})

    log.event("chat_request", message=message)

    # Call Ollama
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": messages,
                "stream": False,
                "tools": TOOLS,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        # Check for tool calls
        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if tool_calls:
            # Execute tools and get final response
            results = []
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name")
                tool_args = tool_call.get("function", {}).get("arguments", {})

                log.event("tool_call", name=tool_name, args=tool_args)
                result = execute_tool(tool_name, tool_args)
                results.append(f"[tool: {tool_name}]\n{result}")

            # Add tool results to messages and get final response
            messages.append({"role": "assistant", "content": msg.get("content", "")})
            messages.append({"role": "user", "content": "\n\n".join(results)})

            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

        reply = data.get("message", {}).get("content", "")
        log.event("chat_response", response_length=len(reply))
        return reply

    except Exception as e:
        log.error("chat_error", str(e))
        return f"error: {e}"


# Create Gradio interface
demo = gr.ChatInterface(
    fn=chat_with_c0rtex,
    title="c0rtex",
    description=f"Privacy-first AI assistant running locally. Chatting as: {USERNAME}",
    examples=[
        "hey, what can you do?",
        "list files in my Documents folder",
        "what's the weather like?",
        "browse to https://example.com and tell me what you see",
    ],
    theme=gr.themes.Soft(
        primary_hue="slate",
        secondary_hue="blue",
    ),
    retry_btn="Retry",
    undo_btn="Undo",
    clear_btn="Clear",
)

if __name__ == "__main__":
    print("Starting c0rtex web interface...")
    print("Open http://localhost:3701 in your browser")
    demo.launch(
        server_name="127.0.0.1",
        server_port=3701,
        share=False,  # Set to True to create public link
    )
