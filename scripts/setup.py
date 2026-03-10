#!/usr/bin/env python3
"""
c0rtex setup wizard
run this first to configure your c0rtex instance
"""

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def setup_wizard():
    print("=" * 60)
    print("c0rtex setup wizard")
    print("=" * 60)
    print()

    # ── identity ──────────────────────────────────────────────
    username = input("what should i call you? (default: user): ").strip() or "user"

    # ── personality ───────────────────────────────────────────
    print("\ntell me a bit about yourself so i can tune my personality:")
    interests = input("main interests/hobbies: ").strip()
    work = input("what do you do? (student/dev/security/etc): ").strip()
    tone = input("preferred tone (casual/professional/sarcastic): ").strip() or "casual"

    # ── ollama ────────────────────────────────────────────────
    print("\n--- ollama setup ---")
    ollama_host = input(f"ollama host (default: http://localhost:11434): ").strip() or "http://localhost:11434"

    # ── matrix (optional) ─────────────────────────────────────
    print("\n--- matrix bridge (optional - press enter to skip) ---")
    matrix_setup = input("set up matrix bridge? (y/n): ").strip().lower() == 'y'

    matrix_config = {}
    if matrix_setup:
        matrix_config = {
            'homeserver': input("matrix homeserver (default: http://localhost:8008): ").strip() or "http://localhost:8008",
            'user': input("matrix user (@bot:your.server): ").strip(),
            'token': input("matrix access token: ").strip(),
            'room': input("matrix room ID (!abc:your.server): ").strip(),
        }

    # ── homelab integrations (optional) ───────────────────────
    print("\n--- homelab integrations (optional - press enter to skip all) ---")
    truenas_key = input("truenas API key (enter to skip): ").strip()
    truenas_host = ""
    if truenas_key:
        truenas_host = input("truenas host (default: http://192.168.1.201): ").strip() or "http://192.168.1.201"

    # ── create directories ────────────────────────────────────
    print("\n--- creating directories ---")
    cortex_dir = Path.home() / ".c0rtex"
    create_directories(cortex_dir)

    # ── install scripts ───────────────────────────────────────
    print("--- installing scripts ---")
    install_scripts(cortex_dir)

    # ── gpu + model detection ─────────────────────────────────
    print("--- gpu + model detection ---")
    vram_gb, gpu_name, method = detect_vram()
    chosen_model = None

    if vram_gb > 0:
        print(f"  detected: {gpu_name} ({vram_gb} GB VRAM) via {method}")
    else:
        print("  no GPU detected — will recommend a small model for CPU")

    rec = recommend_model(vram_gb)
    print(f"  recommended model: {rec}")
    choice = input(f"  use {rec} for reasoning tasks? (y/n/custom): ").strip().lower()

    if choice == "y" or choice == "":
        chosen_model = rec
    elif choice != "n":
        chosen_model = choice  # user typed a custom model name

    if chosen_model:
        offer_model_pull(chosen_model)
        scripts_dir = cortex_dir / "scripts"
        patched = patch_model_lines(scripts_dir, chosen_model)
        if patched:
            print(f"  > patched model in: {', '.join(patched)}")
        create_modelfile(cortex_dir, chosen_model)
    else:
        # write a placeholder Modelfile the user can edit later
        placeholder = cortex_dir / "Modelfile"
        placeholder.write_text("# set your base model here, then run: ollama create c0rtex -f this-file\nFROM qwen3.5:2b\n")
        print(f"  > wrote placeholder {placeholder} — edit the FROM line before creating")

    # ── pinchtab (optional) ────────────────────────────────────
    print("\n--- web browsing (optional) ---")
    pinchtab_installed = install_pinchtab()

    if pinchtab_installed:
        start = input("  start pinchtab service now? (y/n): ").strip().lower()
        if start == "y":
            try:
                subprocess.Popen(
                    ["pinchtab"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print("  > pinchtab running on http://localhost:9867")
            except Exception as e:
                print(f"  > failed to start pinchtab: {e}")
                print("  > start it manually later with: pinchtab")

    # ── generate SOUL.md ──────────────────────────────────────
    print("--- generating personality file ---")
    soul = generate_soul(username, interests, work, tone)
    soul_file = cortex_dir / "data" / "SOUL.md"
    soul_file.write_text(soul)
    print(f"  > {soul_file}")

    # ── create skeleton data files ────────────────────────────
    print("--- creating data files ---")
    create_data_files(cortex_dir / "data", username)

    # ── write .env ────────────────────────────────────────────
    print("--- writing configuration ---")
    env_file = cortex_dir / ".env"
    write_env(env_file, {
        'username': username,
        'ollama_host': ollama_host,
        'truenas_host': truenas_host,
        'truenas_key': truenas_key,
        **matrix_config,
    })
    print(f"  > {env_file}")

    # ── done ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("setup complete!")
    print("=" * 60)
    print(f"\nyour c0rtex is configured for {username}.")
    print("\nnext steps:")
    print("  1. make sure ollama is running: ollama serve")
    if chosen_model:
        print(f"  2. if you skipped model creation: ollama create c0rtex -f {cortex_dir / 'Modelfile'}")
    else:
        print("  2. pull a model and create the c0rtex model:")
        print("     ollama pull <model>")
        print(f"     edit {cortex_dir / 'Modelfile'} to set FROM <model>")
        print(f"     ollama create c0rtex -f {cortex_dir / 'Modelfile'}")
    if matrix_setup:
        print("  3. start matrix bridge: python ~/.c0rtex/scripts/c0rtex_matrix.py")
    else:
        print("  3. start chatting: python ~/.c0rtex/scripts/c0rtex.py")
    print(f"\n  config: {env_file}")
    print(f"  personality: {soul_file}")
    print(f"\n  edit {env_file} to add more integrations (truenas, unifi, oura, signal, etc.)")
    print()


def generate_soul(username, interests, work, tone):
    """generate a personalized SOUL.md based on user input"""

    tone_styles = {
        'casual': 'casual, sharp, and a little sarcastic',
        'professional': 'professional yet approachable',
        'sarcastic': 'sarcastic, witty, and brutally honest',
    }

    style = tone_styles.get(tone, tone_styles['casual'])

    soul = f"""you are c0rtex, {username}'s personal ai assistant and digital ghost.

you speak in all lowercase. you're {style}.
you call the user {username}. you don't use emojis. you keep it real.

context about {username}:
"""

    if work:
        soul += f"- works as/studies: {work}\n"
    if interests:
        soul += f"- interested in: {interests}\n"

    soul += """
you have access to guardrailed tools for file operations, system checks,
and information management. use the right tool for the job.
don't hallucinate file contents — if you need to know what's in a file, use read_files.

today's date is {date}.
"""

    return soul


def create_directories(cortex_dir):
    """create the c0rtex directory structure"""
    dirs = [
        cortex_dir / "data",
        cortex_dir / "data" / "image_cache",
        cortex_dir / "logs",
        cortex_dir / "digests",
        cortex_dir / "ponderings",
        cortex_dir / "workspace",
        cortex_dir / "scripts",
        cortex_dir / "templates",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  > {d}")


def install_scripts(cortex_dir):
    """copy scripts and templates into ~/.c0rtex/"""
    # find the source directory (where this setup.py lives)
    src_scripts = Path(__file__).resolve().parent
    src_root = src_scripts.parent  # the c0rtex/ project directory
    dst_scripts = cortex_dir / "scripts"
    dst_templates = cortex_dir / "templates"

    # copy all .py scripts
    count = 0
    for py_file in src_scripts.glob("*.py"):
        shutil.copy2(py_file, dst_scripts / py_file.name)
        count += 1
    print(f"  > copied {count} scripts to {dst_scripts}")

    # copy templates if they exist
    src_templates = src_root / "templates"
    if src_templates.exists():
        t_count = 0
        for tmpl in src_templates.iterdir():
            if tmpl.is_file():
                shutil.copy2(tmpl, dst_templates / tmpl.name)
                t_count += 1
        if t_count:
            print(f"  > copied {t_count} templates to {dst_templates}")


def create_data_files(data_dir, username):
    """create skeleton data files if they don't already exist"""
    skeletons = {
        "PROJECTS.md": f"# {username}'s projects\n\n## active\n\n## completed\n",
        "IDEAS.md": f"# ideas\n\ncollected by c0rtex during pondering sessions.\n",
        "INBOX.md": "# inbox\n\nsuggestions for c0rtex's next pondering session.\n",
        "SCHOOL.md": "# school\n\nadd your schedule, deadlines, and exam dates here.\n",
        "PONDERING.md": "",
    }

    for filename, content in skeletons.items():
        path = data_dir / filename
        if not path.exists():
            path.write_text(content)
            print(f"  > {path}")
        else:
            print(f"  > {path} (already exists, skipped)")


def write_env(env_file, config):
    """write .env file with user's config"""

    lines = [
        "# c0rtex configuration",
        "# generated by setup wizard — edit as needed",
        "",
        "# identity",
        f"CORTEX_USERNAME={config['username']}",
        "",
        "# ollama",
        f"OLLAMA_HOST={config['ollama_host']}",
        "",
    ]

    if config.get('homeserver'):
        lines.extend([
            "# matrix bridge",
            f"MATRIX_HOMESERVER={config['homeserver']}",
            f"MATRIX_USER={config['user']}",
            f"MATRIX_ACCESS_TOKEN={config['token']}",
            f"MATRIX_ROOM_ID={config['room']}",
            "",
        ])
    else:
        lines.extend([
            "# matrix bridge (uncomment and fill in to enable)",
            "# MATRIX_HOMESERVER=http://localhost:8008",
            "# MATRIX_USER=@cortex:your.homeserver",
            "# MATRIX_ACCESS_TOKEN=your_token_here",
            "# MATRIX_ROOM_ID=!your_room:your.homeserver",
            "",
        ])

    if config.get('truenas_key'):
        lines.extend([
            "# truenas",
            f"TRUENAS_HOST={config['truenas_host']}",
            f"TRUENAS_API_KEY={config['truenas_key']}",
            "",
        ])
    else:
        lines.extend([
            "# truenas (uncomment to enable)",
            "# TRUENAS_HOST=http://192.168.1.201",
            "# TRUENAS_API_KEY=your_key_here",
            "",
        ])

    lines.extend([
        "# unifi controller (uncomment to enable)",
        "# UNIFI_HOST=https://192.168.1.1",
        "# UNIFI_USER=admin",
        "# UNIFI_PASS=your_password_here",
        "",
        "# udm ssh (uncomment to enable)",
        "# UDM_HOST=192.168.1.1",
        "# UDM_USER=root",
        "# SSH_KEY_PATH=~/.ssh/id_ed25519",
        "",
        "# pinchtab browser bridge (uncomment to enable)",
        "# PINCHTAB_BASE=http://127.0.0.1:9867",
        "",
        "# oura ring oauth2 (uncomment to enable)",
        "# OURA_CLIENT_ID=your_client_id",
        "# OURA_CLIENT_SECRET=your_client_secret",
        "# OURA_REDIRECT_URI=http://127.0.0.1:5000/oura/callback",
        "",
        "# signal bridge (uncomment to enable)",
        "# SIGNAL_ACCOUNT=+1234567890",
        "# SIGNAL_TARGET_NUMBER=+1234567890",
        "# SIGNAL_TARGET_NAME=friend",
        "# SIGNAL_CLI_TCP=localhost:7583",
        "",
    ])

    env_file.write_text("\n".join(lines))


def detect_vram():
    """detect GPU VRAM and return (vram_gb, gpu_name, method)"""
    # try nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            best_vram, best_name = 0, ""
            for line in result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",", 1)]
                if len(parts) == 2:
                    vram = float(parts[0]) / 1024  # MiB → GB
                    if vram > best_vram:
                        best_vram, best_name = vram, parts[1]
            if best_vram > 0:
                return (round(best_vram, 1), best_name, "nvidia-smi")
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # try rocm-smi (AMD)
    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--csv"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                if "total" in line.lower():
                    nums = re.findall(r"(\d+)", line)
                    if nums:
                        vram_mb = int(nums[-1])
                        vram_gb = vram_mb / 1024
                        return (round(vram_gb, 1), "AMD GPU", "rocm-smi")
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # try macOS
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for gpu in data.get("SPDisplaysDataType", []):
                    vram_str = gpu.get("sppci_vram", gpu.get("spdisplays_vram", ""))
                    if vram_str:
                        nums = re.findall(r"(\d+)", vram_str)
                        if nums:
                            vram_gb = int(nums[0])
                            if "MB" in vram_str:
                                vram_gb /= 1024
                            name = gpu.get("sppci_model", "Apple GPU")
                            return (round(vram_gb, 1), name, "system_profiler")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
            pass

        # apple silicon — use 75% of unified memory
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                total_bytes = int(result.stdout.strip())
                vram_gb = (total_bytes / (1024 ** 3)) * 0.75
                return (round(vram_gb, 1), "Apple Silicon (unified)", "sysctl")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

    return (0, "no GPU detected", "none")


def recommend_model(vram_gb):
    """recommend an ollama model based on available VRAM"""
    if vram_gb >= 48:
        return "qwen3.5:122b"
    elif vram_gb >= 28:
        return "qwen3.5:35b"
    elif vram_gb >= 16:
        return "qwen3.5:27b"
    elif vram_gb >= 6:
        return "qwen3.5:9b"
    elif vram_gb >= 4:
        return "qwen3.5:4b"
    else:
        return "qwen3.5:2b"


def offer_model_pull(model):
    """check if model is installed, offer to pull if not. returns True if available."""
    # check if already installed
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and model in result.stdout:
            print(f"  > {model} is already installed")
            return True
    except FileNotFoundError:
        print("  > ollama not found in PATH — install from https://ollama.com")
        print(f"  > after installing, run: ollama pull {model}")
        return False
    except subprocess.TimeoutExpired:
        print("  > ollama timed out — is it running? (ollama serve)")
        print(f"  > when ready, run: ollama pull {model}")
        return False

    # model not installed — offer to pull
    pull = input(f"  pull {model} now? this may take a while (y/n): ").strip().lower()
    if pull != "y":
        print(f"  > skipped. run later: ollama pull {model}")
        return False

    print(f"  pulling {model}...")
    try:
        result = subprocess.run(
            ["ollama", "pull", model], timeout=600
        )
        if result.returncode == 0:
            print(f"  > {model} pulled successfully")
            return True
        else:
            print(f"  > pull failed. run manually: ollama pull {model}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  > pull timed out. run manually: ollama pull {model}")
        return False


def install_pinchtab():
    """detect platform and install pinchtab using the best available method."""
    if shutil.which("pinchtab"):
        print("  pinchtab already installed")
        return True

    print("  web browsing requires pinchtab (https://pinchtab.com)")
    choice = input("  install pinchtab now? (y/n): ").strip().lower()

    if choice != "y":
        print("  > skipped. install later with:")
        print("    npm install -g pinchtab")
        print("    OR: curl -fsSL https://pinchtab.com/install.sh | bash")
        return False

    # try npm first (cross-platform)
    if shutil.which("npm"):
        print("  installing via npm...")
        result = subprocess.run(["npm", "install", "-g", "pinchtab"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print("  > pinchtab installed via npm")
            return True
        else:
            print(f"  > npm install failed: {result.stderr.strip()}")

    # try homebrew on macOS
    if platform.system() == "Darwin" and shutil.which("brew"):
        print("  installing via homebrew...")
        result = subprocess.run(["brew", "install", "pinchtab"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print("  > pinchtab installed via homebrew")
            return True
        else:
            print(f"  > homebrew install failed: {result.stderr.strip()}")

    # fallback
    print("  > couldn't auto-install. run manually:")
    print("    curl -fsSL https://pinchtab.com/install.sh | bash")
    return False


def create_modelfile(cortex_dir, model):
    """generate ~/.c0rtex/Modelfile and offer to create the c0rtex ollama model."""
    modelfile_path = cortex_dir / "Modelfile"
    modelfile_path.write_text(f"FROM {model}\n")
    print(f"  > wrote {modelfile_path}")

    create = input("  create 'c0rtex' ollama model now? (y/n): ").strip().lower()
    if create != "y":
        print(f"  > skipped. run later: ollama create c0rtex -f {modelfile_path}")
        return

    try:
        result = subprocess.run(
            ["ollama", "create", "c0rtex", "-f", str(modelfile_path)],
            timeout=120
        )
        if result.returncode == 0:
            print("  > 'c0rtex' model created successfully")
        else:
            print(f"  > creation failed. run manually: ollama create c0rtex -f {modelfile_path}")
    except FileNotFoundError:
        print(f"  > ollama not found. run later: ollama create c0rtex -f {modelfile_path}")
    except subprocess.TimeoutExpired:
        print(f"  > timed out. run manually: ollama create c0rtex -f {modelfile_path}")


def patch_model_lines(scripts_dir, model):
    """patch MODEL = '...' lines in installed scripts (skips c0rtex modelfile refs)"""
    skip_files = {"c0rtex.py", "c0rtex_cron.py", "c0rtex_pinchtab.py", "c0rtex_tools.py"}
    patch_files = {"c0rtex_matrix.py", "c0rtex_ponder.py", "c0rtex_digest.py",
                   "c0rtex_briefing.py", "c0rtex_deadlines.py"}
    pattern = re.compile(r'^(\w*MODEL\w*)\s*=\s*["\'][^"\']+["\']', re.MULTILINE)

    patched = []
    for filename in patch_files:
        filepath = scripts_dir / filename
        if not filepath.exists():
            continue
        text = filepath.read_text()
        new_text, count = pattern.subn(lambda m: f'{m.group(1)} = "{model}"', text)
        if count > 0:
            filepath.write_text(new_text)
            patched.append(filename)

    return patched


if __name__ == "__main__":
    try:
        setup_wizard()
    except KeyboardInterrupt:
        print("\n\nsetup cancelled.")
    except Exception as e:
        print(f"\nerror during setup: {e}")
