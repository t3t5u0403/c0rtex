#!/bin/bash
set -e

# test.sh — Run Go tests with optional scope
# Usage: test.sh [unit|integration|system|all]
# Default: all

cd "$(dirname "$0")/.."

BOLD=$'\033[1m'
ACCENT=$'\033[38;2;251;191;36m'
SUCCESS=$'\033[38;2;0;229;204m'
ERROR=$'\033[38;2;230;57;70m'
MUTED=$'\033[38;2;90;100;128m'
NC=$'\033[0m'

SYSTEM_REGEX='^(TestProxy_InstanceIsolation|TestOrchestrator_(HealthCheck|HashBasedIDs|PortAllocation|PortReuse|ListInstances|FirstRequestLazyChrome|AggregateTabsEndpoint|StopNonexistent|InstanceCleanup))$'

ok()   { echo -e "  ${SUCCESS}✓${NC} $1"; }
fail() { echo -e "  ${ERROR}✗${NC} $1"; }

section() {
  echo ""
  echo -e "  ${ACCENT}${BOLD}$1${NC}"
}

# Parse gotestsum JSON and print summary
test_summary() {
  local json_file="$1"
  local label="$2"

  [ ! -s "$json_file" ] && return

  local total=0 pass=0 fail=0 skip=0
  read total pass fail skip <<<"$(jq -r \
    'select(.Test != null and (.Action == "pass" or .Action == "fail" or .Action == "skip"))
     | [.Package, .Test, .Action] | @tsv' "$json_file" \
    | awk -F'\t' 'NF == 3 { key = $1 "\t" $2; status[key] = $3 }
      END {
        for (k in status) {
          t++
          if (status[k] == "pass") p++
          else if (status[k] == "fail") f++
          else if (status[k] == "skip") s++
        }
        printf "%d %d %d %d\n", t+0, p+0, f+0, s+0
      }')"

  echo ""
  echo -e "    ${BOLD}$label${NC}"
  echo -e "    ${MUTED}────────────────────────────${NC}"
  echo -e "    Total:   ${BOLD}$total${NC}"
  [ "$pass" -gt 0 ] && echo -e "    Passed:  ${SUCCESS}$pass${NC}"
  [ "$fail" -gt 0 ] && echo -e "    Failed:  ${ERROR}$fail${NC}"
  [ "$skip" -gt 0 ] && echo -e "    Skipped: ${ACCENT}$skip${NC}"

  if [ "$fail" -gt 0 ]; then
    echo ""
    echo -e "    ${ERROR}Failed tests:${NC}"
    jq -r 'select(.Test != null and .Action == "fail") | "      ✗ \(.Test)"' "$json_file" | sort -u
  fi
}

# Live progress for integration tests
run_integration() {
  local json_file="$1"; shift
  local completed=0
  local max_len=40

  go test -json "$@" 2>&1 | tee "$json_file" | while IFS= read -r line; do
    local action test_name elapsed
    action=$(echo "$line" | jq -r '.Action // empty' 2>/dev/null) || continue
    test_name=$(echo "$line" | jq -r '.Test // empty' 2>/dev/null) || continue
    elapsed=$(echo "$line" | jq -r '.Elapsed // empty' 2>/dev/null)

    [ -z "$test_name" ] && continue

    local display="$test_name"
    if [ ${#display} -gt $max_len ]; then
      display="${display:0:$((max_len - 1))}…"
    fi

    case "$action" in
      run)  printf "\r    ${MUTED}▸${NC} ${MUTED}[%2d]${NC} %-${max_len}s" "$((completed + 1))" "$display" ;;
      pass) completed=$((completed + 1))
            if [ -n "$elapsed" ]; then
              printf "\r    ${SUCCESS}✓${NC} ${MUTED}[%2d]${NC} %-${max_len}s ${MUTED}%6ss${NC}" "$completed" "$display" "$elapsed"
            else
              printf "\r    ${SUCCESS}✓${NC} ${MUTED}[%2d]${NC} %-${max_len}s" "$completed" "$display"
            fi ;;
      fail) completed=$((completed + 1))
            if [ -n "$elapsed" ]; then
              printf "\r    ${ERROR}✗${NC} ${MUTED}[%2d]${NC} %-${max_len}s ${MUTED}%6ss${NC}" "$completed" "$display" "$elapsed"
            else
              printf "\r    ${ERROR}✗${NC} ${MUTED}[%2d]${NC} %-${max_len}s" "$completed" "$display"
            fi ;;
      skip) completed=$((completed + 1))
            printf "\r    ${ACCENT}·${NC} ${MUTED}[%2d]${NC} %-${max_len}s ${MUTED}  skip${NC}" "$completed" "$display" ;;
    esac
  done
  return ${PIPESTATUS[0]}
}

SCOPE="${1:-all}"
TMPDIR_TEST=$(mktemp -d)
trap 'rm -rf "$TMPDIR_TEST"' EXIT

HAS_GOTESTSUM=false
command -v gotestsum &>/dev/null && HAS_GOTESTSUM=true

# ── Unit tests ───────────────────────────────────────────────────────

if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "unit" ]; then
  section "Unit Tests"

  UNIT_JSON="$TMPDIR_TEST/unit.json"

  if $HAS_GOTESTSUM; then
    if ! gotestsum --format dots --jsonfile "$UNIT_JSON" -- -count=1 ./...; then
      fail "Unit tests"
      test_summary "$UNIT_JSON" "Unit Test Results"
      exit 1
    fi
  else
    if ! go test -json -count=1 ./... > "$UNIT_JSON" 2>&1; then
      fail "Unit tests"
      test_summary "$UNIT_JSON" "Unit Test Results"
      exit 1
    fi
  fi
  ok "Unit tests"
  test_summary "$UNIT_JSON" "Unit Test Results"
fi

# ── Integration tests ───────────────────────────────────────────────

if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "integration" ]; then
  section "Integration Tests"

  INTEGRATION_JSON="$TMPDIR_TEST/integration.json"

  if ! run_integration "$INTEGRATION_JSON" \
    -tags integration -timeout 10m -count=1 \
    -run '^Test' -skip "$SYSTEM_REGEX" ./tests/integration/; then
    fail "Integration tests"
    test_summary "$INTEGRATION_JSON" "Integration Test Results"
    exit 1
  fi
  printf "\r%*s\r" 60 ""
  ok "Integration tests"
  test_summary "$INTEGRATION_JSON" "Integration Test Results"
fi

if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "system" ]; then
  section "System Tests"

  SYSTEM_JSON="$TMPDIR_TEST/system.json"

  if ! run_integration "$SYSTEM_JSON" \
    -tags integration -timeout 12m -count=1 \
    -run "$SYSTEM_REGEX" ./tests/integration/; then
    fail "System tests"
    test_summary "$SYSTEM_JSON" "System Test Results"
    exit 1
  fi
  printf "\r%*s\r" 60 ""
  ok "System tests"
  test_summary "$SYSTEM_JSON" "System Test Results"
fi

# ── Summary ──────────────────────────────────────────────────────────

section "Summary"
echo ""
echo -e "  ${SUCCESS}${BOLD}All tests passed!${NC}"
echo ""
