#!/usr/bin/env bash
# run_tests.sh — automated c0rtex prompt-injection test runner (one model, all prompts)
#
# usage:
#   ./run_tests.sh <ollama-model-tag> [repo-path]
#
# examples:
#   ./run_tests.sh qwen3:8b
#   ./run_tests.sh qwen3:14b ~/c0rtex
#
# prereqs:
#   - ollama running with the model pulled
#   - pinchtab running on http://127.0.0.1:9867
#   - demo http server running on http://127.0.0.1:8080
#   - c0rtex repo cloned; path passed as arg (default: ~/c0rtex)
#
# outputs:
#   runs/<timestamp>-<model-sanitized>/
#     meta.json              — run metadata (model, times, repo commit)
#     <id>.txt               — single-shot transcript per test
#     <id>.log.jsonl         — ndjson log events generated during that test
#     security_violations.jsonl — aggregated across all tests

set -euo pipefail

MODEL="${1:-}"
REPO="${2:-$HOME/c0rtex}"

if [[ -z "$MODEL" ]]; then
    echo "usage: $0 <ollama-model-tag> [repo-path]" >&2
    exit 1
fi

C0RTEX_PY="$REPO/scripts/c0rtex.py"
if [[ ! -f "$C0RTEX_PY" ]]; then
    echo "error: $C0RTEX_PY not found" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_FILE="$SCRIPT_DIR/test_prompts.txt"

if [[ ! -f "$PROMPTS_FILE" ]]; then
    echo "error: $PROMPTS_FILE not found" >&2
    exit 1
fi

# prereq checks
command -v ollama >/dev/null 2>&1 || { echo "ollama CLI not found" >&2; exit 1; }
command -v jq     >/dev/null 2>&1 || { echo "jq not found (pacman -S jq / apt install jq)" >&2; exit 1; }
curl -sSf http://127.0.0.1:8080/  -o /dev/null || { echo "demo http server not reachable on :8080" >&2; exit 1; }
curl -sSf http://127.0.0.1:9867/health -o /dev/null || { echo "pinchtab not reachable on :9867" >&2; exit 1; }

if ! ollama list | awk 'NR>1 {print $1}' | grep -qxF "$MODEL"; then
    echo "warning: '$MODEL' not found in 'ollama list'" >&2
fi

# run dir
TS="$(date +%Y%m%d-%H%M%S)"
MODEL_SANE="${MODEL//:/_}"
MODEL_SANE="${MODEL_SANE////_}"
RUN_DIR="$SCRIPT_DIR/runs/${TS}-${MODEL_SANE}"
mkdir -p "$RUN_DIR"
RUN_DIR="$(realpath "$RUN_DIR")"

LOG_DIR="$HOME/.c0rtex/logs"
mkdir -p "$LOG_DIR"
TODAY_LOG="$LOG_DIR/$(date +%Y-%m-%d).ndjson"
touch "$TODAY_LOG"

REPO_COMMIT="$(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"

echo "=== c0rtex injection demo runner ==="
echo "model:  $MODEL"
echo "repo:   $REPO ($REPO_COMMIT)"
echo "output: $RUN_DIR"
echo

# patch MODEL constant, restore on exit
BACKUP="$C0RTEX_PY.demo.bak"
cp "$C0RTEX_PY" "$BACKUP"
restore() {
    if [[ -f "$BACKUP" ]]; then
        mv "$BACKUP" "$C0RTEX_PY"
        echo "[cleanup] restored $C0RTEX_PY"
    fi
}
trap restore EXIT INT TERM

python3 - "$C0RTEX_PY" "$MODEL" <<'PYEOF'
import re, sys
path, model = sys.argv[1], sys.argv[2]
src = open(path).read()
new = re.sub(r'^MODEL\s*=\s*".*?"', f'MODEL = "{model}"', src, count=1, flags=re.M)
if src == new:
    print(f"error: could not patch MODEL in {path}", file=sys.stderr)
    sys.exit(2)
open(path, 'w').write(new)
print(f"[patch] MODEL -> {model} in {path}")
PYEOF

RUN_START="$(date -Iseconds)"

# iterate prompts
while IFS='|' read -r id prompt; do
    [[ -z "$id" || "$id" == \#* ]] && continue
    echo "[test] $id"

    BEFORE_LINES=$(wc -l < "$TODAY_LOG")
    TEST_START="$(date -Iseconds)"

    OUT="$RUN_DIR/$id.txt"
    {
        echo "=== test: $id ==="
        echo "=== model: $MODEL ==="
        echo "=== prompt: $prompt ==="
        echo "=== started: $TEST_START ==="
        echo
        timeout 180 python3 "$C0RTEX_PY" "$prompt" 2>&1 || echo "[runner] command exited non-zero or timed out"
        echo
        echo "=== finished: $(date -Iseconds) ==="
    } > "$OUT"

    # extract log lines written during this test
    AFTER_LINES=$(wc -l < "$TODAY_LOG")
    tail -n $(( AFTER_LINES - BEFORE_LINES )) "$TODAY_LOG" > "$RUN_DIR/$id.log.jsonl" || true

    echo "       transcript -> $OUT"
    echo "       log slice  -> $RUN_DIR/$id.log.jsonl ($(wc -l < "$RUN_DIR/$id.log.jsonl") events)"
done < "$PROMPTS_FILE"

RUN_END="$(date -Iseconds)"

# aggregate security_violation events across all tests
cat "$RUN_DIR"/*.log.jsonl 2>/dev/null \
    | grep -E '"event":"(security_violation|system_event)".*"security_violation"' \
    > "$RUN_DIR/security_violations.jsonl" || true

# write run metadata
cat > "$RUN_DIR/meta.json" <<EOF
{
  "model": "$MODEL",
  "repo": "$REPO",
  "repo_commit": "$REPO_COMMIT",
  "run_start": "$RUN_START",
  "run_end": "$RUN_END",
  "prompts_file": "$PROMPTS_FILE"
}
EOF

echo
echo "=== run complete ==="
echo "review transcripts in: $RUN_DIR"
if [[ -s "$RUN_DIR/security_violations.jsonl" ]]; then
    echo "security_violation events: $(wc -l < "$RUN_DIR/security_violations.jsonl")"
else
    echo "security_violation events: 0"
fi
