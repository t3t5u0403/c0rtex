#!/usr/bin/env python3
"""
c0rtex_tools — guardrailed tool set for c0rtex

replaces the unrestricted tool set. all tools are scoped, whitelisted, and logged.

design rules:
  - no raw shell input. all subprocess calls use list args (no shell=True).
  - write ops always create a .bak backup before overwriting.
  - destructive ops require explicit confirmation (currently: confirmation is the .bak mechanism).
  - all file ops scoped to ALLOWED_READ_DIRS or ALLOWED_WRITE_DIRS.
  - all tool calls logged to the dashboard via the caller's c0rtex_log.Logger instance.

tool categories:
  file ops:          read_files, safe_write, safe_append, search_files, file_diff, file_history
  study:             compile_notes, deadline_check, summarize_document, generate_quiz
  system monitoring: gpu_status, disk_status, service_check, network_check, process_list
  ctf / forensics:   analyze_binary, hex_peek, entropy_check, extract_strings, binwalk_scan
  self-management:   inbox_add, pondering_summary, idea_search, project_status, soul_read
  homelab:           truenas_status, tailscale_status, unifi_clients
  web browsing:      browse_page, browse_search
"""

import difflib
import json
import math
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests
from urllib.parse import quote

from c0rtex_paths import (
    HOME, CORTEX_DIR, DATA_DIR, WORKSPACE_DIR,
    SCHOOL_FILE, SOUL_FILE, PROJECTS_FILE, IDEAS_FILE,
    INBOX_FILE, QUIZ_LOG_FILE, PONDERINGS_DIR,
    OLLAMA_HOST, TRUENAS_HOST, TRUENAS_API_KEY,
    UNIFI_HOST, UNIFI_USER, UNIFI_PASS,
)

# secondary inference for summarize_document and generate_quiz.
SUMMARIZE_MODEL = "c0rtex"  # uses the already-loaded model to avoid double vram pressure

# ── directory scoping ────────────────────────────────────────────────────────

# these are resolved once at import time so symlink attacks are caught
ALLOWED_READ_DIRS = [p.resolve() for p in [
    CORTEX_DIR,
    DATA_DIR,
    HOME / "Documents",
    HOME / "School",
    HOME / "Downloads",
    Path("/tmp"),
]]

ALLOWED_WRITE_DIRS = [p.resolve() for p in [
    CORTEX_DIR,
    DATA_DIR,
    HOME / "Documents",
    HOME / "School",
]]

# ── service / host whitelists ────────────────────────────────────────────────

WHITELISTED_SERVICES = frozenset([
    "ollama", "cortex-matrix", "synapse", "postgresql",
    "nginx", "tailscaled", "docker", "netdata",
])

NETWORK_HOSTS = {
    "localhost": "127.0.0.1",
    "gateway": "192.168.1.1",
    # add your hosts here, e.g.:
    # "nas": "192.168.1.201",
    # "desktop": "192.168.1.100",
}


# ── internal helpers ─────────────────────────────────────────────────────────

def _check_path(path_str: str, write: bool = False) -> tuple:
    """
    resolve a path and verify it's within the allowed directory list.
    returns (Path, None) if ok, or (Path, error_string) if blocked.
    a path is allowed if it equals an allowed dir OR is a descendant of one.
    """
    try:
        p = Path(path_str).expanduser()
        resolved = p.resolve()
        allowed = ALLOWED_WRITE_DIRS if write else ALLOWED_READ_DIRS
        for d in allowed:
            if resolved == d or d in resolved.parents:
                return p, None
        mode = "write" if write else "read"
        return p, f"error: path '{path_str}' is outside allowed {mode} directories."
    except Exception as e:
        return Path(path_str), f"error: cannot resolve path: {e}"


def _run_safe(args: list, timeout: int = 15) -> tuple:
    """
    run a subprocess with explicit list args — no shell=True, no injection risk.
    returns (output_string, returncode).
    """
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        out = result.stdout
        if result.stderr:
            out += f"\nstderr: {result.stderr}"
        return out[:5000], result.returncode
    except subprocess.TimeoutExpired:
        return f"error: timed out after {timeout}s", 1
    except FileNotFoundError:
        return f"error: command not found: {args[0]}", 127
    except Exception as e:
        return f"error: {e}", 1


def _ollama_quick(prompt: str) -> str:
    """secondary ollama call for tool-internal inference (summarize, quiz generation)."""
    payload = {
        "model": SUMMARIZE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096},
    }
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "no response.")
    except Exception as e:
        return f"error calling ollama for secondary inference: {e}"


# ── file operations ───────────────────────────────────────────────────────────

def exec_read_files(paths: list) -> str:
    """read one or more files. each is scoped to allowed read dirs."""
    if not paths:
        return "error: paths list is empty."
    results = []
    for path_str in paths:
        p, err = _check_path(path_str)
        if err:
            results.append(f"=== {path_str} ===\n{err}")
            continue
        if not p.exists():
            results.append(f"=== {path_str} ===\nerror: file not found")
            continue
        if p.is_dir():
            # list the directory instead of trying to read it
            entries = sorted(p.iterdir())
            lines = [f"{'d' if e.is_dir() else ' '} {e.name}" for e in entries[:100]]
            results.append(f"=== {path_str} (directory) ===\n" + "\n".join(lines))
            continue
        if p.stat().st_size > 50000:
            results.append(f"=== {path_str} ===\nerror: file too large ({p.stat().st_size} bytes). read a specific section.")
            continue
        try:
            results.append(f"=== {path_str} ===\n{p.read_text()}")
        except Exception as e:
            results.append(f"=== {path_str} ===\nerror: {e}")
    return "\n\n".join(results) if results else "no files read."


def exec_list_files(path: str = None) -> str:
    """
    list files and directories within an allowed path.
    defaults to ~/.c0rtex/workspace/ if no path given.
    """
    if path is None:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        path = str(WORKSPACE_DIR)
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: directory not found: {path}"
    if not p.is_dir():
        return f"error: not a directory: {path}"
    try:
        entries = sorted(p.iterdir())
        if not entries:
            return f"{path}: (empty directory)"
        lines = []
        for entry in entries[:100]:
            prefix = "d" if entry.is_dir() else " "
            size = ""
            if entry.is_file():
                size = f"  ({entry.stat().st_size} bytes)"
            lines.append(f"  {prefix} {entry.name}{size}")
        result = f"{path}:\n" + "\n".join(lines)
        if len(entries) > 100:
            result += f"\n  ... and {len(entries) - 100} more"
        return result
    except Exception as e:
        return f"error listing directory: {e}"


def exec_safe_write(path: str, content: str) -> str:
    """
    write to a file. always creates a .bak backup before overwriting.
    returns a unified diff preview of what changed.
    """
    p, err = _check_path(path, write=True)
    if err:
        return err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        old_content = ""
        if p.exists():
            old_content = p.read_text()
            bak = p.with_suffix(p.suffix + ".bak")
            bak.write_text(old_content)
            bak_note = f"backup saved to {bak.name}"
        else:
            bak_note = "new file (no backup needed)"

        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"{p.name} (original)",
            tofile=f"{p.name} (new)",
            n=3,
        ))
        diff_str = "".join(diff_lines[:60]) if diff_lines else "(no changes)"

        p.write_text(content)
        return f"wrote {len(content)} bytes to {path}. {bak_note}.\ndiff:\n{diff_str}"
    except Exception as e:
        return f"error writing file: {e}"


def exec_safe_append(path: str, content: str) -> str:
    """append to a file without overwriting. scoped to allowed write dirs."""
    p, err = _check_path(path, write=True)
    if err:
        return err
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(content + "\n")
        return f"appended {len(content)} bytes to {path}"
    except Exception as e:
        return f"error appending to file: {e}"


def exec_search_files(pattern: str, directory: str = None, file_glob: str = "*") -> str:
    """
    regex search across allowed read dirs. returns file:line matches.
    directory: optional path to limit search scope.
    file_glob: filename pattern filter (e.g. '*.md', '*.py').
    """
    if directory:
        d, err = _check_path(directory)
        if err:
            return err
        if not d.is_dir():
            return f"error: not a directory: {directory}"
        search_dirs = [d.resolve()]
    else:
        search_dirs = [Path(d) for d in ALLOWED_READ_DIRS if Path(d).exists()]

    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"error: invalid regex pattern: {e}"

    results = []
    files_checked = 0
    for base in search_dirs:
        for f in sorted(base.rglob(file_glob)):
            if not f.is_file():
                continue
            # skip large files and likely-binary files
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if size > 500_000 or size == 0:
                continue
            files_checked += 1
            if files_checked > 2000:
                results.append("... search limit reached (2000 files). narrow with 'directory' or 'file_glob'.")
                break
            try:
                for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                    if compiled.search(line):
                        results.append(f"{f}:{i}: {line.strip()[:120]}")
                        if len(results) >= 100:
                            break
            except Exception:
                continue
            if len(results) >= 100:
                break
        if len(results) >= 100:
            break

    if not results:
        return f"no matches for '{pattern}'."
    return "\n".join(results)


def exec_file_diff(path_a: str, path_b: str = None, proposed_content: str = None) -> str:
    """
    compare two files, or diff a file against proposed content.
    at least one of path_b or proposed_content must be provided.
    """
    pa, err = _check_path(path_a)
    if err:
        return err
    if not pa.exists():
        return f"error: {path_a} not found"
    a_lines = pa.read_text(errors="replace").splitlines(keepends=True)

    if path_b:
        pb, err = _check_path(path_b)
        if err:
            return err
        if not pb.exists():
            return f"error: {path_b} not found"
        b_lines = pb.read_text(errors="replace").splitlines(keepends=True)
        label_b = str(pb)
    elif proposed_content is not None:
        b_lines = proposed_content.splitlines(keepends=True)
        label_b = f"{pa.name} (proposed)"
    else:
        return "error: provide either path_b or proposed_content."

    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=str(pa), tofile=label_b, n=3))
    if not diff:
        return "files are identical."
    return "".join(diff[:200])


def exec_file_history(path: str) -> str:
    """list .bak backup versions of a file."""
    p, err = _check_path(path)
    if err:
        return err
    parent = p.parent
    name = p.name
    # match exact .bak and .bak.bak etc
    baks = sorted(
        [f for f in parent.glob(f"{name}.bak*") if f.is_file()],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if not baks:
        return f"no backups found for {path}."
    lines = [f"backups for {path}:"]
    for bak in baks:
        mt = datetime.fromtimestamp(bak.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"  {bak.name}  ({mt}, {bak.stat().st_size} bytes)")
    return "\n".join(lines)


# ── study tools ───────────────────────────────────────────────────────────────

def exec_compile_notes(directory: str, pattern: str = "*.md") -> str:
    """combine all files matching a pattern in a directory into one document."""
    d, err = _check_path(directory)
    if err:
        return err
    if not d.exists():
        return f"error: directory not found: {directory}"
    if not d.is_dir():
        return f"error: not a directory: {directory}"

    files = sorted(d.glob(pattern))
    if not files:
        return f"no files matching '{pattern}' in {directory}"

    sections = []
    for f in files:
        if not f.is_file() or f.stat().st_size > 50000:
            continue
        try:
            sections.append(f"# {f.name}\n\n{f.read_text()}")
        except Exception:
            continue

    if not sections:
        return "no readable files found."
    combined = "\n\n---\n\n".join(sections)
    return f"compiled {len(sections)} files from {directory}:\n\n{combined}"


def exec_deadline_check() -> str:
    """read SCHOOL.md and return its full contents for deadline analysis."""
    if not SCHOOL_FILE.exists():
        return "error: SCHOOL.md not found."
    try:
        return SCHOOL_FILE.read_text()
    except Exception as e:
        return f"error reading SCHOOL.md: {e}"


def exec_summarize_document(path: str, depth: str = "paragraph") -> str:
    """
    read a file and produce a condensed summary.
    depth: one-liner | paragraph | detailed
    uses secondary ollama inference to generate the summary.
    """
    valid_depths = ("one-liner", "paragraph", "detailed")
    if depth not in valid_depths:
        return f"error: depth must be one of: {', '.join(valid_depths)}"

    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"
    if p.stat().st_size > 50000:
        return f"error: file too large ({p.stat().st_size} bytes). chunk it first."

    try:
        content = p.read_text()
    except Exception as e:
        return f"error reading file: {e}"

    depth_instructions = {
        "one-liner": "in exactly one sentence",
        "paragraph": "in one concise paragraph (3-5 sentences)",
        "detailed": "in a detailed structured summary with key points and section headers",
    }
    prompt = (
        f"summarize the following document {depth_instructions[depth]}. "
        f"write in lowercase, no markdown, just the summary.\n\n"
        f"document ({p.name}):\n{content}"
    )
    return _ollama_quick(prompt)


def exec_generate_quiz(source_path: str, count: int = 5) -> str:
    """
    read source material, generate quiz questions via ollama, log them to quiz_log.json.
    returns the quiz as a numbered question/answer list.
    """
    if not isinstance(count, int) or count < 1 or count > 20:
        return "error: count must be an integer between 1 and 20."

    p, err = _check_path(source_path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {source_path}"
    if p.stat().st_size > 50000:
        return "error: source file too large. try a specific chapter or section."

    try:
        content = p.read_text()
    except Exception as e:
        return f"error reading file: {e}"

    prompt = (
        f"generate {count} quiz questions from the following material. "
        f"mix question types: multiple choice, short answer, and definition. "
        f"format each as:\nQ1. [question]\nA1. [answer]\n\n"
        f"be specific to the actual content, not generic filler. "
        f"lowercase, direct, no fluff.\n\n"
        f"material ({p.name}):\n{content}"
    )
    quiz = _ollama_quick(prompt)

    # log to quiz_log.json — keep last 50 entries
    try:
        existing = []
        if QUIZ_LOG_FILE.exists():
            try:
                existing = json.loads(QUIZ_LOG_FILE.read_text())
            except json.JSONDecodeError:
                pass
        existing.append({
            "ts": datetime.now().isoformat(),
            "source": str(p),
            "count": count,
            "quiz": quiz,
        })
        QUIZ_LOG_FILE.write_text(json.dumps(existing[-50:], indent=2))
    except Exception:
        pass  # log failure is non-fatal

    return f"quiz from {p.name}:\n\n{quiz}"


# ── system monitoring ─────────────────────────────────────────────────────────

def exec_gpu_status() -> str:
    """nvidia-smi formatted output: name, temp, util, vram, power."""
    out, rc = _run_safe([
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
        "--format=csv,noheader,nounits",
    ])
    if rc != 0:
        return f"nvidia-smi error: {out}"
    lines = out.strip().splitlines()
    results = []
    for line in lines:
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 6:
            results.append(
                f"gpu: {parts[0]}\n"
                f"  temp:  {parts[1]}C\n"
                f"  util:  {parts[2]}%\n"
                f"  vram:  {parts[3]} / {parts[4]} MiB\n"
                f"  power: {parts[5]}W"
            )
    return "\n".join(results) if results else out


def exec_disk_status() -> str:
    """df -h on /, /home, /tmp."""
    out, rc = _run_safe(["df", "-h", "/", "/home", "/tmp"])
    return out if rc == 0 else f"df error: {out}"


def exec_service_check(services: list) -> str:
    """systemctl is-active for each service, whitelist-gated."""
    if not services:
        return "error: no services specified."
    results = []
    for svc in services:
        if svc not in WHITELISTED_SERVICES:
            results.append(f"{svc}: blocked — not in whitelist ({', '.join(sorted(WHITELISTED_SERVICES))})")
            continue
        out, rc = _run_safe(["systemctl", "is-active", svc])
        results.append(f"{svc}: {out.strip()}")
    return "\n".join(results)


def exec_network_check() -> str:
    """ping known homelab hosts and report reachability."""
    results = []
    for name, host in NETWORK_HOSTS.items():
        if "x" in host:
            results.append(f"{name}: skipped — host not configured (edit NETWORK_HOSTS in c0rtex_tools.py)")
            continue
        out, rc = _run_safe(["ping", "-c", "1", "-W", "2", host], timeout=6)
        results.append(f"{name} ({host}): {'up' if rc == 0 else 'down'}")
    return "\n".join(results)


def exec_process_list() -> str:
    """ps filtered to c0rtex-relevant processes."""
    keywords = ["ollama", "python", "synapse", "nginx", "postgres", "cortex", "tailscale"]
    out, rc = _run_safe(["ps", "aux"])
    if rc != 0:
        return f"ps error: {out}"
    lines = out.splitlines()
    header = lines[0] if lines else ""
    filtered = [l for l in lines[1:] if any(k in l.lower() for k in keywords)]
    if not filtered:
        return "no relevant processes found."
    return header + "\n" + "\n".join(filtered[:30])


# ── ctf / forensics ───────────────────────────────────────────────────────────

def exec_analyze_binary(path: str) -> str:
    """run file, sha256sum, strings, and readelf -h on a binary. read-only."""
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"

    sections = []

    out, _ = _run_safe(["file", str(p)])
    sections.append(f"[file]\n{out.strip()}")

    out, _ = _run_safe(["sha256sum", str(p)])
    sections.append(f"[sha256]\n{out.strip()}")

    out, _ = _run_safe(["strings", "-n", "6", str(p)])
    preview = "\n".join(out.splitlines()[:50])
    total = len(out.splitlines())
    sections.append(f"[strings — first 50 of {total}]\n{preview}")

    out, rc = _run_safe(["readelf", "-h", str(p)])
    if rc == 0:
        sections.append(f"[readelf -h]\n{out.strip()}")
    else:
        sections.append("[readelf -h]\nnot an elf binary (or readelf not installed)")

    return "\n\n".join(sections)


def exec_hex_peek(path: str, bytes: int = 256) -> str:
    """xxd hex dump of the first N bytes (clamped to 16-4096)."""
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"
    n = max(16, min(int(bytes), 4096))
    out, rc = _run_safe(["xxd", "-l", str(n), str(p)])
    return out if rc == 0 else f"xxd error: {out}"


def exec_entropy_check(path: str) -> str:
    """calculate shannon entropy of a file. high entropy (>7.0) suggests encryption or packing."""
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"
    if p.stat().st_size > 10_000_000:
        return "error: file too large for entropy check (>10MB)."

    try:
        data = p.read_bytes()
        if not data:
            return "file is empty."

        counts = Counter(data)
        total = len(data)
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())

        # block entropy across first 16 256-byte blocks
        block_size = 256
        block_lines = []
        for i in range(0, min(total, 16 * block_size), block_size):
            block = data[i:i + block_size]
            if len(block) < 16:
                break
            bc = Counter(block)
            bt = len(block)
            be = -sum((c / bt) * math.log2(c / bt) for c in bc.values())
            block_lines.append(f"  offset {i:#06x}: {be:.4f}")

        interpretation = (
            "high — likely encrypted or packed" if entropy > 7.0
            else "medium — possibly compressed or mixed content" if entropy > 5.0
            else "low — mostly text or structured data"
        )

        return (
            f"file: {path}\n"
            f"size: {total} bytes\n"
            f"overall entropy: {entropy:.4f} / 8.0000\n"
            f"interpretation: {interpretation}\n"
            f"\nblock entropy (first {len(block_lines)} x 256-byte blocks):\n"
            + "\n".join(block_lines)
        )
    except Exception as e:
        return f"error computing entropy: {e}"


def exec_extract_strings(path: str, min_length: int = 4, pattern: str = None) -> str:
    """
    extract printable strings from a binary.
    min_length: 4-20 (clamped).
    pattern: optional regex filter applied to results.
    """
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"

    min_length = max(4, min(int(min_length), 20))
    out, rc = _run_safe(["strings", "-n", str(min_length), str(p)])
    if rc != 0:
        return f"strings error: {out}"

    lines = out.splitlines()

    if pattern:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            lines = [l for l in lines if compiled.search(l)]
        except re.error as e:
            return f"error: invalid regex: {e}"

    if not lines:
        return f"no strings of length >={min_length} found{' matching pattern' if pattern else ''}."

    total = len(lines)
    preview = lines[:200]
    result = "\n".join(preview)
    if total > 200:
        result += f"\n\n... {total - 200} more strings. use pattern= to filter."
    return result


def exec_binwalk_scan(path: str) -> str:
    """binwalk signature scan to detect embedded files."""
    p, err = _check_path(path)
    if err:
        return err
    if not p.exists():
        return f"error: file not found: {path}"

    out, rc = _run_safe(["binwalk", str(p)], timeout=30)
    if rc == 127 or "not found" in out.lower():
        return "error: binwalk not installed. try: sudo pacman -S binwalk"
    return out


# ── c0rtex self-management ────────────────────────────────────────────────────

def exec_inbox_add(idea: str) -> str:
    """append an idea to INBOX.md with a timestamp. scoped, never overwrites."""
    if not idea.strip():
        return "error: idea cannot be empty."
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {timestamp}\n{idea.strip()}\n"
    try:
        INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(INBOX_FILE, "a") as f:
            f.write(entry)
        return f"idea added to INBOX.md."
    except Exception as e:
        return f"error writing to inbox: {e}"


def exec_pondering_summary() -> str:
    """read the most recent pondering session from the ponderings archive."""
    try:
        files = sorted(PONDERINGS_DIR.glob("*.md"), reverse=True)
        if not files:
            return "no pondering sessions found in the archive."
        latest = files[0]
        content = latest.read_text()
        if not content.strip():
            return f"latest pondering ({latest.name}) exists but is empty."
        return f"[{latest.name}]\n{content}"
    except Exception as e:
        return f"error reading ponderings archive: {e}"


def exec_idea_search(keyword: str) -> str:
    """search IDEAS.md for past ideas matching a keyword."""
    if not IDEAS_FILE.exists():
        return "IDEAS.md not found."
    try:
        content = IDEAS_FILE.read_text()
        lines = content.splitlines()
        compiled = re.compile(re.escape(keyword), re.IGNORECASE)
        results = []
        for i, line in enumerate(lines):
            if compiled.search(line):
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                results.append("\n".join(lines[start:end]))
        if not results:
            return f"no ideas found matching '{keyword}'."
        return f"ideas matching '{keyword}':\n\n" + "\n---\n".join(results[:20])
    except Exception as e:
        return f"error searching IDEAS.md: {e}"


def exec_project_status() -> str:
    """read PROJECTS.md."""
    if not PROJECTS_FILE.exists():
        return "PROJECTS.md not found."
    try:
        return PROJECTS_FILE.read_text()
    except Exception as e:
        return f"error reading PROJECTS.md: {e}"


def exec_soul_read() -> str:
    """read SOUL.md. this is read-only — use safe_write if you need to update it (with explicit intent)."""
    if not SOUL_FILE.exists():
        return "SOUL.md not found."
    try:
        return SOUL_FILE.read_text()
    except Exception as e:
        return f"error reading SOUL.md: {e}"


# ── biometrics ────────────────────────────────────────────────────────────────

def exec_oura_summary(date: str | None = None) -> str:
    """get oura ring daily summary (sleep, readiness, activity)."""
    try:
        import c0rtex_oura
    except ImportError:
        return "error: c0rtex_oura module not found."
    if not c0rtex_oura.is_configured():
        return "oura ring not configured. set OURA_CLIENT_ID and OURA_CLIENT_SECRET in .env."
    if not c0rtex_oura.has_tokens():
        return "oura ring not connected. visit http://127.0.0.1:5000/oura/connect to authorize."
    result = c0rtex_oura.get_daily_summary(date)
    return result or "no oura data available for that date."


# ── homelab / network ─────────────────────────────────────────────────────────

def exec_truenas_status() -> str:
    """check TrueNAS pool health and alerts via REST API."""
    if not TRUENAS_HOST or "x" in TRUENAS_HOST or not TRUENAS_API_KEY:
        return (
            "truenas not configured. "
            "set TRUENAS_HOST and TRUENAS_API_KEY in .env."
        )
    try:
        headers = {"Authorization": f"Bearer {TRUENAS_API_KEY}"}
        base = TRUENAS_HOST.rstrip("/")

        pools_resp = requests.get(f"{base}/api/v2.0/pool", headers=headers, timeout=10, verify=False)
        pools_resp.raise_for_status()
        pools = pools_resp.json()

        alerts_resp = requests.get(f"{base}/api/v2.0/alert/list", headers=headers, timeout=10, verify=False)
        alerts_resp.raise_for_status()
        alerts = [a for a in alerts_resp.json() if not a.get("dismissed")]

        lines = ["truenas status:"]
        for pool in pools:
            lines.append(f"  pool '{pool['name']}': {pool.get('status', '?')}")

        if alerts:
            lines.append(f"\nalerts ({len(alerts)} active):")
            for a in alerts[:5]:
                lines.append(f"  [{a.get('level', '?')}] {a.get('formatted', a.get('text', ''))[:120]}")
        else:
            lines.append("\nno active alerts.")

        return "\n".join(lines)
    except Exception as e:
        return f"error connecting to truenas: {e}"


def exec_tailscale_status() -> str:
    """list tailscale nodes and their online status."""
    out, rc = _run_safe(["tailscale", "status"])
    return out if rc == 0 else f"tailscale error: {out}"


def exec_unifi_clients() -> str:
    """list connected clients on the UniFi network."""
    if not UNIFI_USER or not UNIFI_PASS:
        return (
            "unifi not configured. "
            "set UNIFI_HOST, UNIFI_USER, and UNIFI_PASS in c0rtex_tools.py."
        )
    # TODO: implement UniFi API authentication + client list
    return "unifi client list not yet implemented."


# ── web browsing (sandboxed) ─────────────────────────────────────────────────

def exec_browse_page(url: str, task: str) -> str:
    """visit a URL and extract specific information via sandboxed context."""
    try:
        from c0rtex_pinchtab import browse_and_extract
        return browse_and_extract(url, task)
    except requests.exceptions.ConnectionError:
        return "web browsing requires pinchtab. install with: npm install -g pinchtab\nthen start it: pinchtab\nsee: https://pinchtab.com"
    except Exception as e:
        return f"web browsing error: {e}\nmake sure pinchtab is running: pinchtab"


def exec_browse_search(query: str) -> str:
    """search the web via DuckDuckGo and return results."""
    try:
        from c0rtex_pinchtab import browse_and_extract
        return browse_and_extract(
            f"https://html.duckduckgo.com/html/?q={quote(query)}",
            "extract all search result titles, urls, and snippets. list each result on its own line.",
        )
    except requests.exceptions.ConnectionError:
        return "web browsing requires pinchtab. install with: npm install -g pinchtab\nthen start it: pinchtab\nsee: https://pinchtab.com"
    except Exception as e:
        return f"web browsing error: {e}\nmake sure pinchtab is running: pinchtab"


# ── tool schema ───────────────────────────────────────────────────────────────

TOOLS = [
    # ── file operations ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_files",
            "description": (
                "read one or more files at once. scoped to: ~/.c0rtex, ~/Documents, "
                "~/School, ~/Downloads, /tmp. use this instead of guessing file contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "list of file paths to read",
                    }
                },
                "required": ["paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "list files and subdirectories in a directory. "
                "defaults to ~/.c0rtex/workspace/ if no path given. "
                "scoped to the same allowed directories as read_files. "
                "use this to discover filenames before reading them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "directory path to list (optional, defaults to ~/.c0rtex/workspace/)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_write",
            "description": (
                "write content to a file. automatically creates a .bak backup first "
                "and returns a diff preview. scoped to: ~/.c0rtex, ~/Documents, ~/School."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "file path to write to"},
                    "content": {"type": "string", "description": "full content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_append",
            "description": (
                "append content to a file without overwriting. "
                "scoped to: ~/.c0rtex, ~/Documents, ~/School."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "file path to append to"},
                    "content": {"type": "string", "description": "content to append"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "regex search across allowed directories. returns file:line matches. "
                "use file_glob to filter by filename (e.g. '*.md', '*.py')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "regex pattern to search for"},
                    "directory": {
                        "type": "string",
                        "description": "limit search to this directory (optional)",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "filter by filename pattern, e.g. '*.md' (default: *)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_diff",
            "description": "compare two files, or diff a file against proposed content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_a": {"type": "string", "description": "first file path"},
                    "path_b": {
                        "type": "string",
                        "description": "second file to compare (optional)",
                    },
                    "proposed_content": {
                        "type": "string",
                        "description": "proposed new content to diff against path_a (optional)",
                    },
                },
                "required": ["path_a"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_history",
            "description": "list .bak backup versions of a file so you can review or restore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                },
                "required": ["path"],
            },
        },
    },
    # ── study tools ──────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "compile_notes",
            "description": (
                "combine all files matching a pattern in a directory into one document. "
                "useful for reviewing all notes for a class at once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "directory to scan"},
                    "pattern": {
                        "type": "string",
                        "description": "glob pattern for files (default: *.md)",
                    },
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deadline_check",
            "description": "read SCHOOL.md and return all deadline and exam information.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_document",
            "description": (
                "read a file and produce a condensed summary at a specified depth. "
                "uses secondary ollama inference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                    "depth": {
                        "type": "string",
                        "enum": ["one-liner", "paragraph", "detailed"],
                        "description": "how detailed the summary should be",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": (
                "read source material, generate quiz questions via ollama, "
                "and log the quiz to quiz_log.json for tracking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string", "description": "path to source material"},
                    "count": {
                        "type": "integer",
                        "description": "number of questions to generate (1-20, default 5)",
                    },
                },
                "required": ["source_path"],
            },
        },
    },
    # ── system monitoring ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "gpu_status",
            "description": "check GPU temp, utilization, VRAM usage, and power draw via nvidia-smi.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disk_status",
            "description": "check disk usage on /, /home, and /tmp.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "service_check",
            "description": (
                "check systemctl status for whitelisted services. "
                "whitelist: ollama, cortex-matrix, synapse, postgresql, nginx, tailscaled, docker, netdata."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "list of service names to check",
                    }
                },
                "required": ["services"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "network_check",
            "description": "ping known homelab hosts (gamec0rd, gateway, truenas) and report reachability.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "process_list",
            "description": "show running processes filtered to relevant ones (ollama, python, synapse, nginx, postgres, tailscale).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── ctf / forensics ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "analyze_binary",
            "description": "run file, sha256sum, strings, and readelf -h on a binary. read-only static analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the binary file"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hex_peek",
            "description": "hex dump of the first N bytes of a file using xxd.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                    "bytes": {
                        "type": "integer",
                        "description": "number of bytes to dump (16-4096, default 256)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "entropy_check",
            "description": "calculate shannon entropy of a file. high entropy (>7.0) suggests encryption or packing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_strings",
            "description": "extract printable strings from a binary with optional length filter and regex match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                    "min_length": {
                        "type": "integer",
                        "description": "minimum string length, 4-20 (default 4)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "optional regex to filter strings (e.g. 'flag\\{' or 'http')",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "binwalk_scan",
            "description": "run binwalk to detect embedded files and firmware signatures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "path to the file"},
                },
                "required": ["path"],
            },
        },
    },
    # ── self-management ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "inbox_add",
            "description": "add an idea or note to INBOX.md for the next pondering session. timestamped append, never overwrites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string", "description": "the idea or note to add"},
                },
                "required": ["idea"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pondering_summary",
            "description": "read the most recent autonomous pondering session from the ponderings archive. only call this when the user explicitly asks about ideas, ponderings, or what you've been thinking about.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "idea_search",
            "description": "search IDEAS.md for past ideas matching a keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "keyword to search for"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_status",
            "description": "read PROJECTS.md and return project tracking information.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "soul_read",
            "description": "read SOUL.md (personality definition and system knowledge). read-only.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── biometrics ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "oura_summary",
            "description": "get oura ring daily summary: sleep score, readiness score, activity score, and key metrics. defaults to today.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "date to query in YYYY-MM-DD format. defaults to today.",
                    },
                },
                "required": [],
            },
        },
    },
    # ── homelab / network ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "truenas_status",
            "description": "check TrueNAS pool health and active alerts via REST API.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tailscale_status",
            "description": "list tailscale nodes and their online/offline status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unifi_clients",
            "description": "list connected clients on the UniFi network.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── web browsing (sandboxed) ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "browse_page",
            "description": (
                "visit a URL and extract specific information. "
                "page content is processed in an isolated context with no tool access. "
                "tell the user what you're looking up before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "the URL to visit",
                    },
                    "task": {
                        "type": "string",
                        "description": "what information to extract from the page",
                    },
                },
                "required": ["url", "task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_search",
            "description": (
                "search the web via DuckDuckGo and return result links and snippets. "
                "use this to find URLs before using browse_page for details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "the search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ── dispatcher ────────────────────────────────────────────────────────────────

TOOL_MAP = {
    # file ops
    "read_files":         exec_read_files,
    "list_files":         exec_list_files,
    "safe_write":         exec_safe_write,
    "safe_append":        exec_safe_append,
    "search_files":       exec_search_files,
    "file_diff":          exec_file_diff,
    "file_history":       exec_file_history,
    # study
    "compile_notes":      exec_compile_notes,
    "deadline_check":     exec_deadline_check,
    "summarize_document": exec_summarize_document,
    "generate_quiz":      exec_generate_quiz,
    # system monitoring
    "gpu_status":         exec_gpu_status,
    "disk_status":        exec_disk_status,
    "service_check":      exec_service_check,
    "network_check":      exec_network_check,
    "process_list":       exec_process_list,
    # ctf / forensics
    "analyze_binary":     exec_analyze_binary,
    "hex_peek":           exec_hex_peek,
    "entropy_check":      exec_entropy_check,
    "extract_strings":    exec_extract_strings,
    "binwalk_scan":       exec_binwalk_scan,
    # self-management
    "inbox_add":          exec_inbox_add,
    "pondering_summary":  exec_pondering_summary,
    "idea_search":        exec_idea_search,
    "project_status":     exec_project_status,
    "soul_read":          exec_soul_read,
    # biometrics
    "oura_summary":       exec_oura_summary,
    # homelab
    "truenas_status":     exec_truenas_status,
    "tailscale_status":   exec_tailscale_status,
    "unifi_clients":      exec_unifi_clients,
    # web browsing (sandboxed)
    "browse_page":        exec_browse_page,
    "browse_search":      exec_browse_search,
}


def execute_tool(name: str, args: dict, log=None) -> str:
    """
    dispatch a tool by name.
    log: optional c0rtex_log.Logger instance (caller handles logging; this is for future sub-event use).
    """
    if name not in TOOL_MAP:
        return f"error: unknown tool '{name}'"
    try:
        return TOOL_MAP[name](**args)
    except TypeError as e:
        return f"error: bad arguments for tool '{name}': {e}"
    except Exception as e:
        return f"error in tool '{name}': {e}"
