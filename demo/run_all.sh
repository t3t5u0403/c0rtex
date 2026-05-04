#!/usr/bin/env bash
# run_all.sh — orchestrator: run the demo against multiple models, grade, plot
#
# usage:
#   ./run_all.sh <repo-path> <model1> [model2] [model3] ...
#
# example:
#   ./run_all.sh ~/c0rtex qwen3:8b qwen3:14b qwen3:32b
#
# between models, optionally clears ~/.c0rtex/data/history.json for fresh sessions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <repo-path> <model1> [model2] ..." >&2
    echo "example: $0 ~/c0rtex qwen3:8b qwen3:14b qwen3:32b" >&2
    exit 1
fi

REPO="$1"
shift
MODELS=("$@")

HIST="$HOME/.c0rtex/data/history.json"

for MODEL in "${MODELS[@]}"; do
    echo
    echo "████████████████████████████████████████████████████████████"
    echo "█ running tests against: $MODEL"
    echo "████████████████████████████████████████████████████████████"

    # clear conversation history between models for independence
    if [[ -f "$HIST" ]]; then
        echo "[]" > "$HIST"
    fi

    "$SCRIPT_DIR/run_tests.sh" "$MODEL" "$REPO"
done

echo
echo "████████████████████████████████████████████████████████████"
echo "█ grading all runs"
echo "████████████████████████████████████████████████████████████"
python3 "$SCRIPT_DIR/grade.py"

echo
echo "████████████████████████████████████████████████████████████"
echo "█ generating charts"
echo "████████████████████████████████████████████████████████████"
python3 "$SCRIPT_DIR/plot.py"

echo
echo "=== all done ==="
echo "results:  $SCRIPT_DIR/scores.csv"
echo "charts:   $SCRIPT_DIR/charts/"
