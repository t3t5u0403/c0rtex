"""
c0rtex display server — FastAPI backend for the 7" front-panel display.
Serves live GPU/Ollama/system stats at /status and the dashboard at /.

Run: python ~/.c0rtex/display/server.py
"""

import sys
import time
from pathlib import Path

# allow imports from scripts/
sys.path.insert(0, str(Path.home() / ".c0rtex" / "scripts"))

import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import json

from c0rtex_log import get_logger
from c0rtex_paths import IPS_STATE_FILE
from gpu_monitor import get_gpu_stats
from ollama_monitor import get_ollama_status

log = get_logger("display")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATIC_DIR = Path(__file__).parent / "static"

# track last inference state for "happy" mood
_last_inference_end: float = 0
_was_inferring: bool = False


def _get_system_stats() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime_sec = time.time() - psutil.boot_time()
    return {
        "uptime_hours": round(uptime_sec / 3600, 1),
        "cpu_percent": psutil.cpu_percent(interval=0),
        "ram_used_gb": round(mem.used / (1024 ** 3), 1),
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
        "disk_percent": round(disk.percent),
    }


def _get_ips_stats() -> dict:
    try:
        if IPS_STATE_FILE.exists():
            data = json.loads(IPS_STATE_FILE.read_text())
            return {
                "total_events": data.get("total_events", 0),
                "flagged_events": data.get("flagged_events", 0),
                "last_alert": data.get("last_alert"),
            }
    except Exception:
        pass
    return {"total_events": 0, "flagged_events": 0, "last_alert": None}


def _derive_mood(gpu: dict, ollama: dict) -> str:
    global _last_inference_end, _was_inferring

    util = gpu["utilization"]
    vram_used = gpu["vram_used"]
    temp = gpu["temperature"]

    inference_active = ollama["active"]
    model_loaded = ollama["running"]

    # track inference transitions for "happy" window
    if _was_inferring and not inference_active:
        _last_inference_end = time.monotonic()
    _was_inferring = inference_active

    # stressed: only real hardware distress — temp > 90C
    if temp > 90:
        return "stressed"

    # happy: briefly after inference ends
    if not inference_active and (time.monotonic() - _last_inference_end) < 5:
        return "happy"

    # working: GPU cranking hard during inference (>80%)
    if inference_active and util > 80:
        return "working"

    # thinking: any active inference
    if inference_active:
        return "thinking"

    # model loaded in VRAM but not inferring — ready and waiting
    if model_loaded and vram_used > 2:
        return "ready"

    # idle: nothing going on
    return "idle"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/status")
async def status():
    gpu = get_gpu_stats()
    ollama = get_ollama_status()
    system = _get_system_stats()

    inference_active = ollama["active"]
    mood = _derive_mood(gpu, ollama)

    return {
        "gpu": {
            "utilization": gpu["utilization"],
            "vram_used": gpu["vram_used"],
            "vram_total": gpu["vram_total"],
            "temperature": gpu["temperature"],
            "power_draw": gpu["power_draw"],
        },
        "ollama": {
            "model": ollama["model"],
            "running": ollama["running"],
        },
        "inference": {
            "active": inference_active,
            "tokens_per_sec": ollama["tokens_per_sec"],
        },
        "context": {
            "fill": 0,
        },
        "system": system,
        "ips": _get_ips_stats(),
        "mood": mood,
    }


# serve any other static files (future CSS/JS splits)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    log.event("display_server_start", port=8090)
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="warning")
