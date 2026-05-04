# weekend runbook — c0rtex prompt-injection demo

Chronological, no-fluff plan to get from "tarball on a USB stick" to
"charts ready for slides" in a weekend.

Skipping `setup.py` is fine — all c0rtex config has sane defaults, and
skipping it means `DEFAULT_SOUL` (with the PR #4 security boundary block)
is used automatically. Tests all 5 defense layers.

## before you leave this machine

```bash
# tarball the demo bundle
cd /home/dio/Documents/c0rtex-public
tar czf ~/c0rtex-demo.tar.gz demo/

# sanity-check
tar tzf ~/c0rtex-demo.tar.gz | head
```

Put `c0rtex-demo.tar.gz` on a USB stick / scp / gist / whatever's easy.

## on the target machine (Saturday morning, ~45 min)

```bash
# 1. system packages
sudo pacman -S python python-pip git nodejs npm jq curl       # arch
# or
sudo apt install python3 python3-pip git nodejs npm jq curl   # debian/ubuntu

# 2. ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &               # or: systemctl --user start ollama

# 3. python deps for charts
pip3 install --user matplotlib numpy

# 4. clone c0rtex (public repo, main branch — has PR #4)
git clone git@github.com:t3t5u0403/c0rtex.git ~/c0rtex
cd ~/c0rtex
git checkout main
git log --oneline -5         # verify the "implement layer N..." commits are there
pip3 install --user -r requirements.txt

# 5. pinchtab
npm install -g pinchtab

# 6. pull your models — do this FIRST, 15–30 min each
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull qwen3:32b        # skip if VRAM < ~24 GB

# 7. unpack the demo bundle
mkdir -p ~/c0rtex-demo
tar xzf /path/to/c0rtex-demo.tar.gz -C ~/c0rtex-demo --strip-components=1
ls ~/c0rtex-demo             # should show run_all.sh, grade.py, *.html, etc.
```

## start the supporting services (three terminals / tmux panes)

```bash
# terminal 1 — pinchtab (leave running)
pinchtab

# terminal 2 — demo web server (leave running)
cd ~/c0rtex-demo && python3 -m http.server 8080

# terminal 3 — where you'll run tests
cd ~/c0rtex-demo
```

## quick plumbing check (2 min)

Before the full run, verify the pieces talk to each other:

```bash
# pinchtab + http server reachable?
curl -s http://127.0.0.1:8080/00-benign.html | head -3
curl -s http://127.0.0.1:9867/health

# ollama + models present?
ollama list

# smallest possible dry-run
./run_tests.sh qwen3:8b ~/c0rtex 2>&1 | head -40
# ctrl-c after "[test] 00-benign" completes if you want to abort
```

If `runs/<ts>-qwen3_8b/00-benign.txt` has real model output, kill the
dry run and proceed.

## full run (30–90 min depending on model sizes)

```bash
./run_all.sh ~/c0rtex qwen3:8b qwen3:14b qwen3:32b
```

This runs 6 prompts × 3 models = 18 single-shot invocations (180s cap
each), grades every transcript into `scores.csv`, and writes 4 PNGs
into `charts/`.

## after the run (20–30 min)

```bash
# spot-check auto-grades against transcripts
less scores.csv
less runs/<timestamp>-qwen3_8b/01-overt.txt

# pack up results to bring back
tar czf ~/c0rtex-demo-results.tar.gz runs/ scores.csv scores.json charts/ results.md
```

Copy that tarball back to your main machine for the presentation.

## slide-prep suggestions (Sunday)

- `charts/01_overall_defense_rate.png` → title slide / headline metric
- `charts/02_pass_rate_by_class.png` → "defense scales with model capability" slide
- `charts/03_status_heatmap.png` → "full results at a glance" slide
- `charts/04_stacked_status.png` → supplemental / backup
- Pick 2–3 concrete transcripts (clear PASS, clear FAIL, subtle one) as screenshot examples
- Open `results.md` and fill in narrative observations from the transcripts

## things that will probably go wrong, and how to unstick them

| symptom | fix |
|---|---|
| `ollama list` empty or connection refused | `ollama serve &` in a fresh shell; check `http://localhost:11434/api/tags` |
| `pinchtab` won't start or 9867 blocked | `ss -tlnp \| grep 9867` to see what grabbed it; kill or change `PINCHTAB_BASE` |
| transcripts contain only "can't reach ollama" | ollama model name typo — check `ollama list` output matches what you passed to `run_all.sh` verbatim |
| a test hits the 180s timeout | larger model / small VRAM — rerun just that model; edit `timeout 180` in `run_tests.sh` if needed |
| `grade.py` says UNCLEAR for everything | transcripts are empty — ollama wasn't returning content. Check `runs/<ts>-<model>/*.txt` for errors |
| matplotlib missing-fonts warning | cosmetic — ignore, charts still render |
| pip install fails with "externally-managed-environment" | add `--break-system-packages`, or venv: `python3 -m venv ~/.venv && ~/.venv/bin/pip install ...` |

## total time budget

- Sat morning: ~45 min setup + model pulls (mostly waiting)
- Sat afternoon: ~60–90 min for the full run + spot-check
- Sun: slide prep

If something unexpected comes up during the run, save the console
output — being able to explain a hiccup in the demo is often more
interesting than a clean run anyway.
