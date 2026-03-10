"""
c0rtex_paths — single source of truth for all file paths and configuration.

every script imports from here instead of defining its own HOME / CORTEX_DIR / etc.
secrets and config are loaded from ~/.c0rtex/.env at import time.
"""

import os
from pathlib import Path

HOME = Path.home()
CORTEX_DIR = HOME / ".c0rtex"
SCRIPTS_DIR = CORTEX_DIR / "scripts"
DATA_DIR = CORTEX_DIR / "data"
WORKSPACE_DIR = CORTEX_DIR / "workspace"
LOG_DIR = CORTEX_DIR / "logs"
PONDERINGS_DIR = CORTEX_DIR / "ponderings"
DIGESTS_DIR = CORTEX_DIR / "digests"
TEMPLATES_DIR = CORTEX_DIR / "templates"
DISPLAY_DIR = CORTEX_DIR / "display"

# data files
SOUL_FILE = DATA_DIR / "SOUL.md"
SCHOOL_FILE = DATA_DIR / "SCHOOL.md"
PROJECTS_FILE = DATA_DIR / "PROJECTS.md"
IDEAS_FILE = DATA_DIR / "IDEAS.md"
INBOX_FILE = DATA_DIR / "INBOX.md"
PONDERING_FILE = DATA_DIR / "PONDERING.md"
HISTORY_FILE = DATA_DIR / "history.json"
MATRIX_HISTORY_FILE = DATA_DIR / "matrix_history.json"
IMAGE_CACHE_DIR = DATA_DIR / "image_cache"
DIGEST_SEEN_FILE = DATA_DIR / "digest_seen.json"
DIGEST_QUEUE_FILE = DATA_DIR / "digest_queue.json"
QUIZ_LOG_FILE = DATA_DIR / "quiz_log.json"
IPS_STATE_FILE = DATA_DIR / "ips_state.json"
IPS_SEEN_FILE = DATA_DIR / "ips_seen.json"
OURA_TOKENS_FILE = DATA_DIR / "oura_tokens.json"
SIGNAL_HISTORY_FILE = DATA_DIR / "signal_history.json"
SIGNAL_SOUL_FILE = DATA_DIR / "signalsoul.md"
SIGNAL_ENABLED_FILE = DATA_DIR / "signal_enabled"

# ── .env loader ─────────────────────────────────────────────────────────────

ENV_FILE = CORTEX_DIR / ".env"


def load_env():
    """load KEY=VALUE pairs from .env into os.environ (setdefault — real env wins)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # strip optional quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env()

# ── config constants (from env) ─────────────────────────────────────────────

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

MATRIX_HOMESERVER = os.environ.get("MATRIX_HOMESERVER", "http://localhost:8008")
MATRIX_USER = os.environ.get("MATRIX_USER", "")
MATRIX_ACCESS_TOKEN = os.environ.get("MATRIX_ACCESS_TOKEN", "")
MATRIX_ROOM_ID = os.environ.get("MATRIX_ROOM_ID", "")

TRUENAS_HOST = os.environ.get("TRUENAS_HOST", "http://192.168.1.201")
TRUENAS_API_KEY = os.environ.get("TRUENAS_API_KEY", "")

UNIFI_HOST = os.environ.get("UNIFI_HOST", "https://192.168.1.1")
UNIFI_USER = os.environ.get("UNIFI_USER", "")
UNIFI_PASS = os.environ.get("UNIFI_PASS", "")

UDM_HOST = os.environ.get("UDM_HOST", "192.168.1.1")
UDM_USER = os.environ.get("UDM_USER", "root")
SSH_KEY_PATH = Path(os.environ.get("SSH_KEY_PATH", str(HOME / ".ssh" / "id_ed25519"))).expanduser()

PINCHTAB_BASE = os.environ.get("PINCHTAB_BASE", "http://127.0.0.1:9867")

OURA_CLIENT_ID = os.environ.get("OURA_CLIENT_ID", "")
OURA_CLIENT_SECRET = os.environ.get("OURA_CLIENT_SECRET", "")
OURA_REDIRECT_URI = os.environ.get("OURA_REDIRECT_URI", "http://127.0.0.1:5000/oura/callback")

SIGNAL_ACCOUNT = os.environ.get("SIGNAL_ACCOUNT", "")
SIGNAL_TARGET_NUMBER = os.environ.get("SIGNAL_TARGET_NUMBER", "")
SIGNAL_TARGET_NAME = os.environ.get("SIGNAL_TARGET_NAME", "")
SIGNAL_CLI_TCP = os.environ.get("SIGNAL_CLI_TCP", "localhost:7583")

# user identity (set by setup wizard)
USERNAME = os.environ.get("CORTEX_USERNAME", "user")
