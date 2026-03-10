#!/usr/bin/env python3
"""
c0rtex setup wizard
run this first to configure your c0rtex instance
"""

import os
import shutil
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
    print("  2. create a modelfile or pull a model: ollama pull qwen3:4b")
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


if __name__ == "__main__":
    try:
        setup_wizard()
    except KeyboardInterrupt:
        print("\n\nsetup cancelled.")
    except Exception as e:
        print(f"\nerror during setup: {e}")
