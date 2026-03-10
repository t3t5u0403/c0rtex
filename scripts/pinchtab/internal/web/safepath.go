package web

import (
	"fmt"
	"path/filepath"
	"strings"
)

// SafePath resolves a user-provided path against a base directory and ensures
// the result stays within that directory. Returns the cleaned absolute path.
//
// The implementation uses the filepath.Abs + strings.HasPrefix pattern
// recommended by CodeQL (go/path-injection) and OWASP path-traversal guidance.
func SafePath(base, userPath string) (string, error) {
	absBase, err := filepath.Abs(base)
	if err != nil {
		return "", fmt.Errorf("invalid base path: %w", err)
	}

	// Empty or "." means the base directory itself.
	if userPath == "" || userPath == "." {
		return absBase, nil
	}

	// Reject absolute paths outright — user input must be relative to base.
	if filepath.IsAbs(userPath) || strings.HasPrefix(userPath, "/") || strings.HasPrefix(userPath, string(filepath.Separator)) {
		return "", fmt.Errorf("absolute paths not allowed: %q", userPath)
	}

	// Go 1.20+: reject paths with "..", device names (NUL, CON on Windows),
	// and other non-local components.
	if !filepath.IsLocal(userPath) {
		return "", fmt.Errorf("path %q contains invalid components", userPath)
	}

	// Join, clean, resolve to absolute.
	joined := filepath.Join(absBase, userPath)
	absPath, err := filepath.Abs(joined)
	if err != nil {
		return "", fmt.Errorf("invalid resolved path: %w", err)
	}

	// Final containment check — the resolved path must be under absBase.
	if !strings.HasPrefix(absPath, absBase+string(filepath.Separator)) && absPath != absBase {
		return "", fmt.Errorf("path %q escapes base directory %q", userPath, absBase)
	}

	return absPath, nil
}
