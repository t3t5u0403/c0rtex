#!/usr/bin/env bash
set -euo pipefail

# doctor.sh — Verify and setup development environment for pinchtab
# Interactive: asks before installing anything

BOLD='\033[1m'
ACCENT='\033[38;2;251;191;36m'      # yellow #fbbf24
INFO='\033[38;2;136;146;176m'       # muted #8892b0
SUCCESS='\033[38;2;0;229;204m'      # cyan #00e5cc
ERROR='\033[38;2;230;57;70m'        # red #e63946
MUTED='\033[38;2;90;100;128m'       # text-muted #5a6480
NC='\033[0m'

CRITICAL=0
WARNINGS=0

# ── Helpers ──────────────────────────────────────────────────────────

ok()      { echo -e "  ${SUCCESS}✓${NC} $1"; }
fail()    { echo -e "  ${ERROR}✗${NC} $1"; [ -n "${2:-}" ] && echo -e "    ${MUTED}$2${NC}"; CRITICAL=$((CRITICAL + 1)); }
warn()    { echo -e "  ${ACCENT}·${NC} $1"; [ -n "${2:-}" ] && echo -e "    ${MUTED}$2${NC}"; WARNINGS=$((WARNINGS + 1)); }
hint()    { echo -e "    ${MUTED}$1${NC}"; }

confirm() {
  echo -ne "    ${BOLD}$1 [y/N]${NC} "
  read -r answer
  [[ "$answer" =~ ^[Yy]$ ]]
}

section() {
  echo ""
  echo -e "${ACCENT}${BOLD}$1${NC}"
}

# ── Detect package manager ───────────────────────────────────────────

HAS_BREW=false
HAS_APT=false
command -v brew &>/dev/null && HAS_BREW=true
command -v apt-get &>/dev/null && HAS_APT=true

# ── Start ────────────────────────────────────────────────────────────

echo ""
echo -e "  ${ACCENT}${BOLD}🦀 Pinchtab Doctor${NC}"
echo -e "  ${INFO}Verifying and setting up development environment...${NC}"

section "Go Backend"

# ── Go ───────────────────────────────────────────────────────────────

if command -v go &>/dev/null; then
  GO_VERSION=$(go version | awk '{print $3}' | sed 's/go//')
  GO_MAJOR=$(echo "$GO_VERSION" | cut -d. -f1)
  GO_MINOR=$(echo "$GO_VERSION" | cut -d. -f2)

  if [ "$GO_MAJOR" -ge 1 ] && [ "$GO_MINOR" -ge 25 ]; then
    ok "Go $GO_VERSION"
  else
    fail "Go $GO_VERSION — requires 1.25+"
    if $HAS_BREW && confirm "Install latest Go via brew?"; then
      brew install go && ok "Go installed" && CRITICAL=$((CRITICAL - 1))
    else
      hint "Install from https://go.dev/dl/"
    fi
  fi
else
  fail "Go not found"
  if $HAS_BREW && confirm "Install Go via brew?"; then
    brew install go && ok "Go installed" && CRITICAL=$((CRITICAL - 1))
  else
    hint "Install from https://go.dev/dl/"
  fi
fi

# ── golangci-lint ────────────────────────────────────────────────────

if command -v golangci-lint &>/dev/null; then
  LINT_VERSION=$(golangci-lint version --short 2>/dev/null || golangci-lint --version 2>/dev/null | head -1 | awk '{print $4}')
  ok "golangci-lint $LINT_VERSION"
else
  fail "golangci-lint" "Required for pre-commit hooks and CI."
  if $HAS_BREW && confirm "Install golangci-lint via brew?"; then
    brew install golangci-lint && ok "golangci-lint installed" && CRITICAL=$((CRITICAL - 1))
  elif command -v go &>/dev/null && confirm "Install golangci-lint via go install?"; then
    go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest && ok "golangci-lint installed" && CRITICAL=$((CRITICAL - 1))
  else
    hint "brew install golangci-lint"
    hint "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"
  fi
fi

# ── Git hooks ────────────────────────────────────────────────────────

if [ -f ".git/hooks/pre-commit" ]; then
  ok "Git hooks"
else
  warn "Git hooks not installed"
  if confirm "Install git hooks now?"; then
    if ./scripts/install-hooks.sh 2>/dev/null; then
      ok "Git hooks installed"
      WARNINGS=$((WARNINGS - 1))
    else
      cp scripts/pre-commit .git/hooks/pre-commit
      chmod +x .git/hooks/pre-commit
      ok "Git hooks installed"
      WARNINGS=$((WARNINGS - 1))
    fi
  fi
fi

# ── Go dependencies ─────────────────────────────────────────────────

if [ -f "go.mod" ]; then
  if go list -m all &>/dev/null 2>&1; then
    ok "Go dependencies"
  else
    warn "Go dependencies not downloaded"
    if confirm "Download Go dependencies?"; then
      go mod download && ok "Go dependencies downloaded" && WARNINGS=$((WARNINGS - 1))
    fi
  fi
fi

section "Dashboard (React/TypeScript)"

if [ -d "dashboard" ]; then

  # ── Node.js ──────────────────────────────────────────────────────

  if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)

    if [ "$NODE_MAJOR" -ge 18 ]; then
      ok "Node.js $NODE_VERSION"
    else
      warn "Node.js $NODE_VERSION — 18+ recommended"
      if $HAS_BREW && confirm "Install latest Node.js via brew?"; then
        brew install node && ok "Node.js installed" && WARNINGS=$((WARNINGS - 1))
      else
        hint "Install from https://nodejs.org"
      fi
    fi
  else
    warn "Node.js not found" "Optional — needed for dashboard."
    if $HAS_BREW && confirm "Install Node.js via brew?"; then
      brew install node && ok "Node.js installed" && WARNINGS=$((WARNINGS - 1))
    else
      hint "Install from https://nodejs.org"
    fi
  fi

  # ── Bun ────────────────────────────────────────────────────────

  if command -v bun &>/dev/null; then
    ok "Bun $(bun -v)"
  else
    warn "Bun not found" "Optional — used for fast dashboard builds."
    if confirm "Install Bun?"; then
      curl -fsSL https://bun.sh/install | bash && ok "Bun installed (restart shell to use)" && WARNINGS=$((WARNINGS - 1))
    else
      hint "curl -fsSL https://bun.sh/install | bash"
    fi
  fi

  # ── Dashboard deps ─────────────────────────────────────────────

  if [ -d "dashboard/node_modules" ]; then
    ok "Dashboard dependencies"
  else
    warn "Dashboard dependencies not installed"
    if command -v bun &>/dev/null; then
      if confirm "Install dashboard dependencies via bun?"; then
        (cd dashboard && bun install) && ok "Dashboard dependencies installed" && WARNINGS=$((WARNINGS - 1))
      fi
    elif command -v npm &>/dev/null; then
      if confirm "Install dashboard dependencies via npm?"; then
        (cd dashboard && npm install) && ok "Dashboard dependencies installed" && WARNINGS=$((WARNINGS - 1))
      fi
    else
      hint "cd dashboard && bun install"
    fi
  fi

else
  echo -e "  ${MUTED}Dashboard directory not found (optional)${NC}"
fi

# ── Summary ──────────────────────────────────────────────────────────

section "Summary"
echo ""

if [ $CRITICAL -eq 0 ] && [ $WARNINGS -eq 0 ]; then
  echo -e "  ${SUCCESS}${BOLD}All checks passed!${NC} You're ready to develop."
  echo ""
  echo -e "  ${MUTED}Next steps:${NC}"
  echo -e "    ${MUTED}go build ./cmd/pinchtab${NC}"
  echo -e "    ${MUTED}go test ./...${NC}"
  exit 0
fi

[ $CRITICAL -gt 0 ] && echo -e "  ${ERROR}✗${NC} $CRITICAL critical issue(s) remaining"
[ $WARNINGS -gt 0 ] && echo -e "  ${ACCENT}·${NC} $WARNINGS warning(s)"

if [ $CRITICAL -gt 0 ]; then
  echo ""
  echo -e "  ${MUTED}After installing, run ./doctor.sh again.${NC}"
  exit 1
fi

exit 0
