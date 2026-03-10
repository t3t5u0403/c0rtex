# Scripts

Development and CI scripts for PinchTab.

> **Tip:** Use `./pdev` from the repo root for an interactive command picker, or `./pdev <command>` to run directly.

## Quality

| Script | Purpose |
|--------|---------|
| `check.sh` | Go checks (format, vet, build, lint) |
| `check-dashboard.sh` | Dashboard checks (typecheck, eslint, prettier) |
| `check-gosec.sh` | Security scan with gosec (reproduces CI security job) |
| `check-docs-json.sh` | Validate `docs/index.json` structure |
| `test.sh` | Go test runner with progress (unit, integration, system, or all) |
| `pre-commit` | Git pre-commit hook (format + lint) |

## Build & Run

| Script | Purpose |
|--------|---------|
| `build-dashboard.sh` | Generate TS types (tygo) + build React dashboard + copy to Go embed |
| `dev.sh` | Full build (dashboard + Go) and run |

## Setup

| Script | Purpose |
|--------|---------|
| `doctor.sh` | Verify & setup dev environment (interactive — prompts before installing) |
| `install-hooks.sh` | Install git pre-commit hook |

## Testing

| Script | Purpose |
|--------|---------|
| `simulate-memory-load.sh` | Memory load testing |
| `simulate-ratelimit-leak.sh` | Rate limit leak testing |
