#!/usr/bin/env python3
"""
c0rtex web dashboard.
reads logs, conversation history, ponderings, and digests.

usage:
    python c0rtex_web.py
    open http://127.0.0.1:5000
"""

import json
from datetime import date

from flask import Flask, abort, jsonify, redirect, render_template, request

from c0rtex_paths import (
    LOG_DIR, PONDERINGS_DIR, DIGESTS_DIR,
    HISTORY_FILE, MATRIX_HISTORY_FILE, TEMPLATES_DIR,
    SIGNAL_HISTORY_FILE, SIGNAL_ENABLED_FILE, SIGNAL_TARGET_NAME,
)

app = Flask(__name__, template_folder=str(TEMPLATES_DIR))


def read_log_file(date_str: str) -> list:
    log_file = LOG_DIR / f"{date_str}.ndjson"
    if not log_file.exists():
        return []
    entries = []
    for line in log_file.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def load_json_file(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def list_archive(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    return sorted([f.stem for f in directory.glob("*.md")], reverse=True)


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    today = date.today().isoformat()
    entries = read_log_file(today)

    sessions: dict[str, int] = {}
    errors = 0
    ollama_calls = 0
    tool_calls = 0
    for entry in entries:
        evt = entry.get("event", "")
        if evt == "session_start":
            src = entry.get("source", "unknown")
            sessions[src] = sessions.get(src, 0) + 1
        elif evt == "error":
            errors += 1
        elif evt == "ollama_request":
            ollama_calls += 1
        elif evt == "tool_call":
            tool_calls += 1

    recent = list(reversed(entries[-20:]))

    last_pondering = next(iter(list_archive(PONDERINGS_DIR)), None)
    last_digest = next(iter(list_archive(DIGESTS_DIR)), None)

    return render_template(
        "index.html",
        sessions=sessions,
        errors=errors,
        ollama_calls=ollama_calls,
        tool_calls=tool_calls,
        recent=recent,
        last_pondering=last_pondering,
        last_digest=last_digest,
        today=today,
    )


@app.route("/conversations")
def conversations():
    cli = list(reversed(load_json_file(HISTORY_FILE)))
    matrix = list(reversed(load_json_file(MATRIX_HISTORY_FILE)))
    return render_template("conversations.html", cli_history=cli, matrix_history=matrix)


@app.route("/ponderings")
def ponderings():
    return render_template("ponderings.html", files=list_archive(PONDERINGS_DIR))


@app.route("/ponderings/<name>")
def pondering(name):
    if "/" in name or ".." in name:
        abort(404)
    f = PONDERINGS_DIR / f"{name}.md"
    if not f.exists():
        abort(404)
    return render_template("pondering.html", name=name, content=f.read_text())


@app.route("/digests")
def digests():
    return render_template("digests.html", files=list_archive(DIGESTS_DIR))


@app.route("/digests/<name>")
def digest(name):
    if "/" in name or ".." in name:
        abort(404)
    f = DIGESTS_DIR / f"{name}.md"
    if not f.exists():
        abort(404)
    return render_template("digest.html", name=name, content=f.read_text())


@app.route("/logs")
def logs():
    today = date.today().isoformat()
    selected = request.args.get("date", today)
    available = sorted([f.stem for f in LOG_DIR.glob("*.ndjson")], reverse=True) if LOG_DIR.exists() else []
    return render_template("logs.html", selected_date=selected, available_dates=available)


@app.route("/api/logs")
def api_logs():
    date_str = request.args.get("date", date.today().isoformat())
    source_filter = request.args.get("source", "")
    event_filter = request.args.get("event", "")
    entries = read_log_file(date_str)
    if source_filter:
        entries = [e for e in entries if e.get("source") == source_filter]
    if event_filter:
        entries = [e for e in entries if e.get("event") == event_filter]
    return jsonify(entries)


# ── signal bridge ─────────────────────────────────────────────────────────────

@app.route("/signal")
def signal():
    enabled = SIGNAL_ENABLED_FILE.exists()
    history = load_json_file(SIGNAL_HISTORY_FILE)
    recent = list(reversed(history[-20:]))
    return render_template(
        "signal.html",
        enabled=enabled,
        target_name=SIGNAL_TARGET_NAME,
        message_count=len(history),
        recent=recent,
    )


# ── oura ring ────────────────────────────────────────────────────────────────

@app.route("/oura")
def oura():
    import c0rtex_oura
    configured = c0rtex_oura.is_configured()
    connected = c0rtex_oura.has_tokens()
    summary = None
    if connected:
        try:
            summary = c0rtex_oura.get_latest_summary()
        except Exception:
            summary = None
    return render_template("oura.html", configured=configured, connected=connected, summary=summary)


@app.route("/oura/connect")
def oura_connect():
    import c0rtex_oura
    if not c0rtex_oura.is_configured():
        abort(400, "oura client credentials not configured in .env")
    return redirect(c0rtex_oura.get_auth_url())


@app.route("/oura/callback")
def oura_callback():
    import c0rtex_oura
    code = request.args.get("code")
    if not code:
        abort(400, "missing authorization code")
    if c0rtex_oura.exchange_code(code):
        return redirect("/oura")
    abort(500, "token exchange failed — check logs")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
