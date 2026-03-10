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

from InquirerPy import inquirer, get_style
from InquirerPy.separator import Separator
from InquirerPy.base.control import Choice
from InquirerPy.utils import color_print

STYLE = get_style({
    "questionmark": "#ff9d00 bold",
    "answer": "#61afef bold",
    "input": "#ffffff",
    "pointer": "#ff9d00 bold",
    "checkbox": "#61afef",
    "instruction": "#6c7086 italic",
}, style_override=False)

BANNER = r"""
   ___  ___       _
  / __\/ _ \ _ __| |_ _____  __
 / /  | | | | '__| __/ _ \ \/ /
/ /___| |_| | |  | ||  __/>  <
\____/ \___/|_|   \__\___/_/\_\
"""


def section(title):
    color_print([("\n", ""), ("#ff9d00 bold", f"  {title}\n")])


def ok(msg):
    print(f"  \033[32m✓\033[0m {msg}")


def fail(msg):
    print(f"  \033[31m✗\033[0m {msg}")


def info(msg):
    print(f"  \033[36m→\033[0m {msg}")


def setup_wizard():
    print(BANNER)
    color_print([("#ff9d00 bold", "  setup wizard\n")])

    # ── identity ──────────────────────────────────────────────
    section("identity")
    username = inquirer.text(
        message="what should i call you?",
        default="user",
        style=STYLE,
    ).execute()

    # ── personality ───────────────────────────────────────────
    section("personality")
    info("tell me a bit about yourself so i can tune my personality")
    interests = inquirer.text(
        message="interests/hobbies:",
        long_instruction="(optional)",
        style=STYLE,
    ).execute()
    work = inquirer.text(
        message="what do you do?",
        long_instruction="(optional)",
        style=STYLE,
    ).execute()
    tone = inquirer.select(
        message="preferred tone:",
        choices=[
            Choice(value="casual", name="casual — chill, sharp, a little sarcastic"),
            Choice(value="professional", name="professional — clean and approachable"),
            Choice(value="sarcastic", name="sarcastic — witty and brutally honest"),
        ],
        default="casual",
        style=STYLE,
    ).execute()

    # ── ollama ────────────────────────────────────────────────
    section("ollama")
    ollama_host = inquirer.text(
        message="ollama host:",
        default="http://localhost:11434",
        style=STYLE,
    ).execute()

    # ── matrix (optional) ─────────────────────────────────────
    section("matrix bridge")
    matrix_setup = inquirer.confirm(
        message="set up matrix bridge?",
        default=False,
        style=STYLE,
    ).execute()

    matrix_config = {}
    if matrix_setup:
        matrix_config = {
            'homeserver': inquirer.text(
                message="matrix homeserver:",
                default="http://localhost:8008",
                style=STYLE,
            ).execute(),
            'user': inquirer.text(
                message="matrix user (@bot:your.server):",
                style=STYLE,
            ).execute(),
            'token': inquirer.text(
                message="matrix access token:",
                style=STYLE,
            ).execute(),
            'room': inquirer.text(
                message="matrix room ID (!abc:your.server):",
                style=STYLE,
            ).execute(),
        }

    # ── homelab integrations (optional) ───────────────────────
    section("homelab integrations")
    truenas_key = inquirer.text(
        message="truenas API key:",
        long_instruction="(enter to skip)",
        style=STYLE,
    ).execute()
    truenas_host = ""
    if truenas_key:
        truenas_host = inquirer.text(
            message="truenas host:",
            default="http://192.168.1.201",
            style=STYLE,
        ).execute()

    # ── create directories ────────────────────────────────────
    section("creating directories")
    cortex_dir = Path.home() / ".c0rtex"
    create_directories(cortex_dir)

    # ── install scripts ───────────────────────────────────────
    section("installing scripts")
    install_scripts(cortex_dir)

    # ── gpu + model detection ─────────────────────────────────
    section("gpu + model detection")
    vram_gb, gpu_name, method = detect_vram()
    chosen_model = None

    if vram_gb > 0:
        ok(f"detected: {gpu_name} ({vram_gb} GB VRAM) via {method}")
    else:
        info("no GPU detected — will recommend a small model for CPU")

    rec = recommend_model(vram_gb)

    all_models = [
        "qwen3.5:2b",
        "qwen3.5:4b",
        "qwen3.5:9b",
        "qwen3.5:27b",
        "qwen3.5:35b",
        "qwen3.5:122b",
    ]

    model_choices = []
    for m in all_models:
        label = f"{m}  [recommended]" if m == rec else m
        model_choices.append(Choice(value=m, name=label))
    model_choices.append(Separator())
    model_choices.append(Choice(value="__custom__", name="Custom..."))
    model_choices.append(Choice(value="__skip__", name="Skip"))

    model_pick = inquirer.select(
        message="select model for reasoning tasks:",
        choices=model_choices,
        default=rec,
        style=STYLE,
    ).execute()

    if model_pick == "__custom__":
        chosen_model = inquirer.text(
            message="model name:",
            style=STYLE,
        ).execute()
    elif model_pick == "__skip__":
        chosen_model = None
    else:
        chosen_model = model_pick

    if chosen_model:
        offer_model_pull(chosen_model)
        scripts_dir = cortex_dir / "scripts"
        patched = patch_model_lines(scripts_dir, chosen_model)
        if patched:
            ok(f"patched model in: {', '.join(patched)}")
        create_modelfile(cortex_dir, chosen_model)
    else:
        # write a placeholder Modelfile the user can edit later
        placeholder = cortex_dir / "Modelfile"
        placeholder.write_text("# set your base model here, then run: ollama create c0rtex -f this-file\nFROM qwen3.5:2b\n")
        info(f"wrote placeholder {placeholder} — edit the FROM line before creating")

    # ── pinchtab (optional) ────────────────────────────────────
    section("web browsing")
    color_print([
        ("", "  c0rtex can browse the web using Pinchtab for research.\n\n"),
        ("#ff9d00 bold", "  security note: "),
        ("", "web browsing uses prompt-based isolation to protect\n"),
        ("", "  against malicious websites. while this works well in most cases,\n"),
        ("", "  it's not 100% foolproof against sophisticated prompt injection.\n"),
        ("", "  only browse sites you trust.\n"),
    ])
    pinchtab_installed = install_pinchtab()

    if pinchtab_installed:
        start = inquirer.confirm(
            message="start pinchtab service now?",
            default=False,
            style=STYLE,
        ).execute()
        if start:
            try:
                subprocess.Popen(
                    ["pinchtab"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                ok("pinchtab running on http://localhost:9867")
            except Exception as e:
                fail(f"failed to start pinchtab: {e}")
                info("start it manually later with: pinchtab")

    # ── generate SOUL.md ──────────────────────────────────────
    section("generating personality file")
    soul = generate_soul(username, interests, work, tone)
    soul_file = cortex_dir / "data" / "SOUL.md"
    soul_file.write_text(soul)
    ok(str(soul_file))

    # ── create skeleton data files ────────────────────────────
    section("creating data files")
    create_data_files(cortex_dir / "data", username)

    # ── write .env ────────────────────────────────────────────
    section("writing configuration")
    env_file = cortex_dir / ".env"
    write_env(env_file, {
        'username': username,
        'ollama_host': ollama_host,
        'truenas_host': truenas_host,
        'truenas_key': truenas_key,
        **matrix_config,
    })
    ok(str(env_file))

    # ── done ──────────────────────────────────────────────────
    pinchtab_status = "installed" if pinchtab_installed else "skipped"
    matrix_status = "configured" if matrix_setup else "skipped"

    print()
    print("  \033[33m══════════════════════════════════════════\033[0m")
    print("  \033[32m✓\033[0m setup complete!")
    print("  \033[33m══════════════════════════════════════════\033[0m")
    print()
    print(f"  configured for: \033[1m{username}\033[0m")
    print(f"  model: \033[1m{chosen_model or 'none (placeholder written)'}\033[0m")
    print(f"  pinchtab: {pinchtab_status}")
    print(f"  matrix: {matrix_status}")
    print()
    print("  \033[1mnext steps:\033[0m")
    print("    1. ollama serve")
    if chosen_model:
        print(f"    2. python ~/.c0rtex/scripts/c0rtex.py")
    else:
        print("    2. pull a model and create the c0rtex model:")
        print("       ollama pull <model>")
        print(f"       edit {cortex_dir / 'Modelfile'} to set FROM <model>")
        print(f"       ollama create c0rtex -f {cortex_dir / 'Modelfile'}")
    if matrix_setup:
        print("    3. start matrix bridge: python ~/.c0rtex/scripts/c0rtex_matrix.py")
    else:
        print("    3. start chatting: python ~/.c0rtex/scripts/c0rtex.py")
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
        ok(str(d))


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
    ok(f"copied {count} scripts to {dst_scripts}")

    # copy templates if they exist
    src_templates = src_root / "templates"
    if src_templates.exists():
        t_count = 0
        for tmpl in src_templates.iterdir():
            if tmpl.is_file():
                shutil.copy2(tmpl, dst_templates / tmpl.name)
                t_count += 1
        if t_count:
            ok(f"copied {t_count} templates to {dst_templates}")


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
            ok(str(path))
        else:
            info(f"{path} (already exists, skipped)")


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
            ok(f"{model} is already installed")
            return True
    except FileNotFoundError:
        fail("ollama not found in PATH — install from https://ollama.com")
        info(f"after installing, run: ollama pull {model}")
        return False
    except subprocess.TimeoutExpired:
        fail("ollama timed out — is it running? (ollama serve)")
        info(f"when ready, run: ollama pull {model}")
        return False

    # model not installed — offer to pull
    pull = inquirer.confirm(
        message=f"pull {model} now? this may take a while",
        default=True,
        style=STYLE,
    ).execute()
    if not pull:
        info(f"skipped. run later: ollama pull {model}")
        return False

    info(f"pulling {model}...")
    try:
        result = subprocess.run(
            ["ollama", "pull", model], timeout=600
        )
        if result.returncode == 0:
            ok(f"{model} pulled successfully")
            return True
        else:
            fail(f"pull failed. run manually: ollama pull {model}")
            return False
    except subprocess.TimeoutExpired:
        fail(f"pull timed out. run manually: ollama pull {model}")
        return False


def install_pinchtab():
    """detect platform and install pinchtab using the best available method."""
    if shutil.which("pinchtab"):
        ok("pinchtab already installed")
        return True

    install = inquirer.confirm(
        message="install pinchtab for web browsing?",
        default=False,
        style=STYLE,
    ).execute()

    if not install:
        info("skipped. install later with:")
        print("    npm install -g pinchtab")
        print("    OR: curl -fsSL https://pinchtab.com/install.sh | bash")
        return False

    # try npm first (cross-platform)
    if shutil.which("npm"):
        info("installing via npm...")
        result = subprocess.run(["npm", "install", "-g", "pinchtab"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            ok("pinchtab installed via npm")
            return True
        else:
            fail(f"npm install failed: {result.stderr.strip()}")

    # try homebrew on macOS
    if platform.system() == "Darwin" and shutil.which("brew"):
        info("installing via homebrew...")
        result = subprocess.run(["brew", "install", "pinchtab"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            ok("pinchtab installed via homebrew")
            return True
        else:
            fail(f"homebrew install failed: {result.stderr.strip()}")

    # fallback
    fail("couldn't auto-install. run manually:")
    print("    curl -fsSL https://pinchtab.com/install.sh | bash")
    return False


def create_modelfile(cortex_dir, model):
    """generate ~/.c0rtex/Modelfile and offer to create the c0rtex ollama model."""
    modelfile_path = cortex_dir / "Modelfile"
    modelfile_path.write_text(f"FROM {model}\n")
    ok(f"wrote {modelfile_path}")

    create = inquirer.confirm(
        message="create 'c0rtex' ollama model now?",
        default=True,
        style=STYLE,
    ).execute()
    if not create:
        info(f"skipped. run later: ollama create c0rtex -f {modelfile_path}")
        return

    try:
        result = subprocess.run(
            ["ollama", "create", "c0rtex", "-f", str(modelfile_path)],
            timeout=120
        )
        if result.returncode == 0:
            ok("'c0rtex' model created successfully")
        else:
            fail(f"creation failed. run manually: ollama create c0rtex -f {modelfile_path}")
    except FileNotFoundError:
        fail(f"ollama not found. run later: ollama create c0rtex -f {modelfile_path}")
    except subprocess.TimeoutExpired:
        fail(f"timed out. run manually: ollama create c0rtex -f {modelfile_path}")


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
        print("\n\n  setup cancelled.")
    except Exception as e:
        print(f"\n  error during setup: {e}")
