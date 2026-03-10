"""
c0rtex structured logging.
writes NDJSON events to ~/.c0rtex/logs/YYYY-MM-DD.ndjson.

usage:
    from c0rtex_log import get_logger
    log = get_logger("myscript")
    log.session_start()
    log.ollama_request(MODEL, messages, tools=True)
    log.ollama_response(MODEL, content, duration_ms)
    log.session_end()
"""

import json
from datetime import datetime, date

from c0rtex_paths import LOG_DIR


class Logger:
    def __init__(self, source: str):
        self.source = source

    def _write(self, event: str, **data):
        try:
            entry = {
                "ts": datetime.now().isoformat(),
                "source": self.source,
                "event": event,
                **data,
            }
            log_file = LOG_DIR / f"{date.today().isoformat()}.ndjson"
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # never crash the calling script

    def session_start(self, **kwargs):
        self._write("session_start", **kwargs)

    def session_end(self, **kwargs):
        self._write("session_end", **kwargs)

    def ollama_request(self, model: str, messages: list, *, stream=False, think=False, tools=False):
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), None
        )
        self._write(
            "ollama_request",
            model=model,
            message_count=len(messages),
            last_user_message=last_user,
            stream=stream,
            think=think,
            tools=tools,
        )

    def ollama_response(self, model: str, content: str, duration_ms: int, *,
                        tool_call_names=None, thinking=None):
        self._write(
            "ollama_response",
            model=model,
            content=content,
            duration_ms=duration_ms,
            tool_call_names=tool_call_names or [],
            thinking=thinking,
        )

    def tool_call(self, name: str, args: dict):
        self._write("tool_call", name=name, args=args)

    def tool_result(self, name: str, result: str, duration_ms: int):
        self._write(
            "tool_result",
            name=name,
            result=result[:500] if len(result) > 500 else result,
            duration_ms=duration_ms,
        )

    def error(self, error_type: str, message: str):
        self._write("error", error_type=error_type, message=message)

    def event(self, name: str, **data):
        self._write("system_event", name=name, **data)

    def matrix_in(self, content: str):
        self._write("matrix_message_in", content=content)

    def matrix_out(self, content: str):
        self._write("matrix_message_out", content=content)


def get_logger(source: str) -> Logger:
    """get a logger for a specific script. source is a short name like 'c0rtex' or 'matrix'."""
    return Logger(source)
