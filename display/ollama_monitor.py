"""
ollama_monitor — Ollama status checker for the display server. Testing
"""

import requests

_OLLAMA = "http://localhost:11434"
_TIMEOUT = 3


def get_ollama_status() -> dict:
    result = {
        "model": None,
        "running": False,
        "active": False,
        "tokens_per_sec": 0.0,
    }

    try:
        resp = requests.get(f"{_OLLAMA}/api/ps", timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models", [])
        if models:
            m = models[0]
            result["model"] = m.get("model", "unknown")
            result["running"] = True
            # if there's an active inference, size_vram > 0 and expires_at is in the future
            # but more reliably, check if the model is loaded
            result["active"] = m.get("size_vram", 0) > 0
    except Exception:
        pass

    return result
