#!/usr/bin/env python3
"""
c0rtex_tui — CRT/cyberpunk terminal interface
green phosphor on black. ascii borders. glitch effects. the whole deal.
"""

import json
import random
import time
import requests
from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Input, Static

from c0rtex_log import get_logger
from c0rtex_tools import TOOLS, execute_tool
from c0rtex_paths import CORTEX_DIR, HISTORY_FILE, SOUL_FILE, OLLAMA_HOST, USERNAME

log = get_logger("tui")

# ── config ──────────────────────────────────────────────────────────────────
MODEL = "c0rtex"
MAX_HISTORY = 50
VERSION = "1.0"

STARTUP_GLITCHES = [
    "c0rd5lut is online",
    "cables tangled",
    "ghost in the wire",
    "signal acquired",
    "tetsuo was here",
]

FOOTER_FLICKERS = [
    "[SIGNAL:NOMINAL]",
    "[PATCH:4/8 CONNECTED]",
    "[LINK:STABLE]",
    "[FEED:LIVE]",
    "[CORE:INTACT]",
    "[MESH:SYNCED]",
]

ABOUT_ART = r"""
     ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗
    ██╔════╝██╔═████╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝
    ██║     ██║██╔██║██████╔╝   ██║   █████╗   ╚███╔╝
    ██║     ████╔╝██║██╔══██╗   ██║   ██╔══╝   ██╔██╗
    ╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗
     ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝

    local ai assistant — personal digital ghost
    tetsuo approved. no cloud. no leash.
"""

DEFAULT_SOUL = f"""you are c0rtex, {USERNAME}'s personal ai assistant and digital ghost.
you speak in all lowercase. you're casual, sharp, and a little sarcastic.
you call the user {USERNAME}. you don't use emojis. you keep it real.
you have access to guardrailed tools for file operations, system checks,
and information management. use the right tool for the job.
don't hallucinate file contents — if you need to know what's in a file, use read_files.
today's date is {{date}}.
"""


LEET_MAP = str.maketrans("aeiostlAEIOSTL", "43105714310571")


def glitchify(text: str) -> str:
    """Corrupt text with leetspeak substitutions."""
    return text.translate(LEET_MAP)


# ── soul / history ──────────────────────────────────────────────────────────

def load_soul():
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text()
    else:
        soul = DEFAULT_SOUL
    return soul.replace("{date}", datetime.now().strftime("%A, %B %d, %Y"))


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_history(messages: list):
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    trimmed = messages[-MAX_HISTORY:]
    HISTORY_FILE.write_text(json.dumps(trimmed, indent=2))


# ── widgets ─────────────────────────────────────────────────────────────────

class HeaderBar(Static):
    """CRT-style machine interface header."""

    pulse_on = reactive(True)
    conn_ok = reactive(True)

    def render(self) -> str:
        indicator = "◉" if self.pulse_on else "◎"
        if self.conn_ok:
            bar = "██████████░░"
            return f" ▌c0rtex v{VERSION}▐   {bar}  SYS:OK   {indicator} ONLINE "
        else:
            bar = "██░░░░░░░░░░"
            return f" ▌c0rtex v{VERSION}▐   {bar}  SYS:ERR  {indicator} OFFLINE "

    def toggle_pulse(self) -> None:
        self.pulse_on = not self.pulse_on

    def set_conn(self, ok: bool) -> None:
        self.conn_ok = ok


class StatusFooter(Static):
    """Flickering CRT footer."""

    flicker_text = reactive("")

    def render(self) -> str:
        if self.flicker_text:
            return f" {self.flicker_text} "
        return " ▌READY▐ "

    def set_flicker(self, text: str) -> None:
        self.flicker_text = text

    def clear_flicker(self) -> None:
        self.flicker_text = ""


class ChatMessage(Static):
    """A single chat message with CRT box-drawing frame."""

    def __init__(self, role: str, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.msg_content = content

    def render(self) -> str:
        if self.role == "user":
            return f"┌─ you ─\n│ {self.msg_content}\n└─"
        elif self.role == "assistant":
            return f"┌─ c0rtex ─\n│ {self.msg_content}\n└─"
        elif self.role == "tool_call":
            return self.msg_content
        elif self.role == "error":
            return self.msg_content
        elif self.role == "system":
            return self.msg_content
        return self.msg_content

    def update_content(self, content: str) -> None:
        self.msg_content = content
        self.refresh()


class LoadingIndicator(Static):
    """Animated loading widget — data stream style."""

    frame = reactive(0)

    def render(self) -> str:
        # cycling progress bar: [■■□□□□] receiving...
        pos = self.frame % 6
        bar = "■" * (pos + 1) + "□" * (5 - pos)
        return f"  [{bar}] receiving..."

    def advance(self) -> None:
        self.frame += 1


# ── main app ────────────────────────────────────────────────────────────────

class C0rtexApp(App):

    CSS = """
    Screen {
        background: #000000;
    }

    #header-bar {
        dock: top;
        height: 1;
        background: #001100;
        color: #00ff41;
        text-style: bold;
    }

    #header-bar.conn-lost {
        background: #110000;
        color: #ff3333;
    }

    #chat {
        scrollbar-color: #005500;
        scrollbar-color-hover: #00ff41;
        background: #000000;
        margin: 0 1;
    }

    .user-msg {
        color: #00ff41;
        margin: 1 0 0 0;
        padding: 0 1;
    }

    .assistant-msg {
        color: #00ff41;
        margin: 1 0 0 0;
        padding: 0 1;
    }

    .tool-call {
        color: #ff9d00;
        text-style: dim;
        margin: 0 2;
    }

    .error-msg {
        color: #ff3333;
        text-style: bold;
        margin: 1 0;
        padding: 0 1;
    }

    .system-msg {
        color: #005500;
        text-style: italic;
        margin: 1 0;
        padding: 0 1;
    }

    .loading {
        color: #005500;
        margin: 0 2;
    }

    #input-box {
        dock: bottom;
        border: tall #005500;
        background: #000000;
        color: #00ff41;
        margin: 0 1;
    }

    #input-box:focus {
        border: tall #00ff41;
    }

    #input-box.flash {
        border: tall #41ff83;
        background: #001a00;
    }

    #status-footer {
        dock: bottom;
        height: 1;
        background: #001100;
        color: #005500;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "quit"),
        Binding("ctrl+l", "clear_chat", "clear"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.soul = load_soul()
        self.history: list = load_history()
        self.messages: list = [{"role": "system", "content": self.soul}] + self.history
        self._loading_widget: LoadingIndicator | None = None
        self._loading_timer = None

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        yield VerticalScroll(id="chat")
        yield StatusFooter(id="status-footer")
        yield Input(placeholder="▶ speak...", id="input-box")

    def on_mount(self) -> None:
        log.session_start()

        # render existing history
        chat = self.query_one("#chat")
        for msg in self.history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                w = ChatMessage("user", content, classes="user-msg")
                chat.mount(w)
            elif role == "assistant":
                w = ChatMessage("assistant", content, classes="assistant-msg")
                chat.mount(w)
            elif role == "tool":
                # skip tool results in display — they were shown as handshakes
                pass

        # startup message
        startup = "c0rtex online. ctrl+c to quit."
        if random.randint(1, 10) == 1:
            glitch = random.choice(STARTUP_GLITCHES)
            startup = f"{glitch}... {startup}"
        w = ChatMessage("system", startup, classes="system-msg")
        chat.mount(w)

        # pulse timer for header
        self.set_interval(1.2, self._pulse_header)
        # footer flicker timer
        self.set_interval(8.0, self._flicker_footer)
        # connection check timer
        self._check_connection()
        self.set_interval(15.0, self._check_connection)

        self.query_one("#input-box").focus()

    def _pulse_header(self) -> None:
        self.query_one(HeaderBar).toggle_pulse()

    def _flicker_footer(self) -> None:
        footer = self.query_one(StatusFooter)
        if random.randint(1, 3) == 1:
            footer.set_flicker(random.choice(FOOTER_FLICKERS))
            self.set_timer(2.0, footer.clear_flicker)

    @work(thread=True, exclusive=True, group="conn_check")
    def _check_connection(self) -> None:
        """Ping ollama to see if it's reachable."""
        try:
            requests.get(f"{OLLAMA_HOST}/api/version", timeout=3)
            ok = True
        except Exception:
            ok = False

        def _update():
            header = self.query_one(HeaderBar)
            header.set_conn(ok)
            if ok:
                header.remove_class("conn-lost")
            else:
                header.add_class("conn-lost")

        self.call_from_thread(_update)

    def _flash_input(self) -> None:
        """Brief border flash on the input box."""
        inp = self.query_one("#input-box")
        inp.add_class("flash")
        self.set_timer(0.15, lambda: inp.remove_class("flash"))

    def _scroll_to_bottom(self) -> None:
        chat = self.query_one("#chat")
        chat.scroll_end(animate=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return
        event.input.value = ""
        self._flash_input()

        # commands
        if user_input.lower() in ("/exit", "exit"):
            self.exit()
            return

        if user_input.lower() in ("/clear", "clear"):
            self.action_clear_chat()
            return

        if user_input.lower() == "/about":
            self._show_about()
            return

        # add user message to chat
        chat = self.query_one("#chat")
        w = ChatMessage("user", user_input, classes="user-msg")
        chat.mount(w)
        self._scroll_to_bottom()

        user_msg = {"role": "user", "content": user_input}
        self.messages.append(user_msg)
        self.history.append(user_msg)

        # disable input while processing
        self.query_one("#input-box").disabled = True

        self.send_message()

    def _show_about(self) -> None:
        chat = self.query_one("#chat")
        w = ChatMessage("system", ABOUT_ART, classes="system-msg")
        chat.mount(w)
        self._scroll_to_bottom()

    def _add_loading(self) -> None:
        chat = self.query_one("#chat")
        self._loading_widget = LoadingIndicator(classes="loading")
        chat.mount(self._loading_widget)
        self._scroll_to_bottom()
        self._loading_timer = self.set_interval(0.4, self._advance_loading)

    def _advance_loading(self) -> None:
        if self._loading_widget:
            self._loading_widget.advance()

    def _remove_loading(self) -> None:
        if self._loading_timer:
            self._loading_timer.stop()
            self._loading_timer = None
        if self._loading_widget:
            self._loading_widget.remove()
            self._loading_widget = None

    def _add_assistant_msg(self, content: str) -> ChatMessage:
        chat = self.query_one("#chat")
        w = ChatMessage("assistant", content, classes="assistant-msg")
        chat.mount(w)
        self._scroll_to_bottom()
        return w

    def _add_tool_call(self, text: str) -> None:
        chat = self.query_one("#chat")
        w = ChatMessage("tool_call", text, classes="tool-call")
        chat.mount(w)
        self._scroll_to_bottom()

    def _add_error(self, text: str) -> None:
        chat = self.query_one("#chat")
        w = ChatMessage("error", text, classes="error-msg")
        chat.mount(w)
        self._scroll_to_bottom()

    @work(thread=True)
    def send_message(self) -> None:
        """Run the ollama chat loop in a background thread."""
        self.call_from_thread(self._add_loading)

        max_tool_rounds = 10
        for _round in range(max_tool_rounds):
            result = self._do_chat_request()
            if result is None:
                break

            tool_calls = result.get("tool_calls")

            if tool_calls:
                # save assistant message with tool calls
                history_msg = {
                    "role": "assistant",
                    "content": result.get("content", ""),
                    "tool_calls": tool_calls,
                }
                self.messages.append(history_msg)
                self.history.append(history_msg)

                # execute each tool
                for tool_call in tool_calls:
                    func = tool_call["function"]
                    tool_name = func["name"]
                    tool_args = func.get("arguments", {})

                    self.call_from_thread(
                        self._add_tool_call,
                        f"╶──┤ {tool_name} ├────── running... ──╴",
                    )

                    log.tool_call(tool_name, tool_args)
                    t0 = time.time()
                    try:
                        tool_result = execute_tool(tool_name, tool_args)
                    except Exception as e:
                        tool_result = f"tool error: {e}"
                        log.error("tool_exec", str(e))

                    elapsed = int((time.time() - t0) * 1000)
                    log.tool_result(tool_name, tool_result, elapsed)

                    # update the handshake line (add a new one with timing)
                    self.call_from_thread(
                        self._add_tool_call,
                        f"╶──┤ {tool_name} ├── {elapsed}ms ──╴",
                    )

                    tool_msg = {"role": "tool", "content": tool_result}
                    self.messages.append(tool_msg)
                    self.history.append(tool_msg)

                # loop back for next response
                self.call_from_thread(self._add_loading)
                continue

            else:
                # text response — already streamed into widget
                content = result.get("content", "...")
                assistant_msg = {"role": "assistant", "content": content}
                self.messages.append(assistant_msg)
                self.history.append(assistant_msg)
                break

        save_history(self.history)

        # re-enable input
        def _reenable():
            inp = self.query_one("#input-box")
            inp.disabled = False
            inp.focus()
        self.call_from_thread(_reenable)

    def _do_chat_request(self) -> dict | None:
        """Make a streaming request to ollama. Streams tokens into the UI."""
        payload = {
            "model": MODEL,
            "messages": self.messages,
            "stream": True,
            "tools": TOOLS,
            "options": {"num_ctx": 8192},
        }

        log.ollama_request(MODEL, self.messages, stream=True, tools=True)
        t0 = time.time()

        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=300,
                stream=True,
            )
            resp.raise_for_status()

            full_content = ""
            full_tool_calls = []
            widget = None

            for line in resp.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line)
                msg = chunk.get("message", {})

                if msg.get("tool_calls"):
                    full_tool_calls.extend(msg["tool_calls"])

                token = msg.get("content", "")
                if token:
                    full_content += token
                    if widget is None:
                        self.call_from_thread(self._remove_loading)
                        widget = self.call_from_thread(self._add_assistant_msg, full_content)
                    else:
                        self.call_from_thread(widget.update_content, full_content)
                        self.call_from_thread(self._scroll_to_bottom)

                if chunk.get("done"):
                    self.call_from_thread(self._remove_loading)
                    elapsed = int((time.time() - t0) * 1000)
                    tc_names = [tc["function"]["name"] for tc in full_tool_calls] if full_tool_calls else []
                    log.ollama_response(MODEL, full_content, elapsed, tool_call_names=tc_names)
                    return {
                        "role": "assistant",
                        "content": full_content,
                        "tool_calls": full_tool_calls if full_tool_calls else None,
                    }

            # stream ended without done flag
            self.call_from_thread(self._remove_loading)
            elapsed = int((time.time() - t0) * 1000)
            log.ollama_response(MODEL, full_content or "...", elapsed)
            return {
                "role": "assistant",
                "content": full_content or "...",
                "tool_calls": full_tool_calls if full_tool_calls else None,
            }

        except requests.exceptions.Timeout:
            log.error("timeout", "ollama timed out")
            self.call_from_thread(self._remove_loading)
            self.call_from_thread(self._show_fault, "timeout", "ollama timed out. try again?")
            return None

        except requests.exceptions.ConnectionError:
            log.error("connection", "cannot reach ollama")
            self.call_from_thread(self._remove_loading)
            self.call_from_thread(self._show_fault, "connection refused", "can't reach ollama. is it running?")
            return None

        except Exception as e:
            log.error("unknown", str(e))
            self.call_from_thread(self._remove_loading)
            self.call_from_thread(self._show_fault, "corrupted response", str(e)[:40])
            return None

    def _show_fault(self, fault_type: str, detail: str) -> None:
        """Render a glitched system fault block."""
        glitched = glitchify(fault_type.upper())
        self._add_error(
            f"╔═══ SYSTEM FAULT ═══════════════════════╗\n"
            f"║ ▓▒░ {glitched:<34} ░▒▓ ║\n"
            f"║ {detail:<40} ║\n"
            f"╚════════════════════════════════════════╝"
        )

    def action_clear_chat(self) -> None:
        """Clear chat history and UI."""
        self.history.clear()
        self.messages = [{"role": "system", "content": self.soul}]
        save_history(self.history)

        chat = self.query_one("#chat")
        chat.remove_children()

        w = ChatMessage("system", "history cleared.", classes="system-msg")
        chat.mount(w)

    def action_quit(self) -> None:
        log.session_end()
        self.exit()


# ── entry point ─────────────────────────────────────────────────────────────

def main():
    CORTEX_DIR.mkdir(parents=True, exist_ok=True)
    app = C0rtexApp()
    app.run()


if __name__ == "__main__":
    main()
