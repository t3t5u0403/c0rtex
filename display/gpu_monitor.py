"""
gpu_monitor — cached nvidia-smi wrapper for the display server.
"""

import subprocess
import time

_cache = {"ts": 0, "data": None}
_CACHE_TTL = 2  # seconds

_DEFAULTS = {"utilization": 0, "vram_used": 0.0, "vram_total": 0.0, "temperature": 0, "power_draw": 0}


def get_gpu_stats() -> dict:
    now = time.monotonic()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["data"]

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return _DEFAULTS

        parts = [x.strip() for x in result.stdout.strip().split(",")]
        if len(parts) < 6:
            return _DEFAULTS

        data = {
            "utilization": int(parts[2]),
            "vram_used": round(float(parts[3]) / 1024, 1),
            "vram_total": round(float(parts[4]) / 1024, 1),
            "temperature": int(parts[1]),
            "power_draw": round(float(parts[5])),
        }
        _cache["data"] = data
        _cache["ts"] = now
        return data

    except Exception:
        return _DEFAULTS
