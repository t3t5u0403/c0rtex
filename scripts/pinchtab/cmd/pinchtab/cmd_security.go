package main

import (
	"bufio"
	"fmt"
	"os"
	"reflect"
	"strings"

	"github.com/pinchtab/pinchtab/internal/config"
)

func handleSecurityCommand(cfg *config.RuntimeConfig) {
	warnings := assessSecurityWarnings(cfg)
	recommended := recommendedSecurityDefaultLines(cfg)

	fmt.Println("Security posture:")
	fmt.Println()
	printSecuritySummary(os.Stdout, cfg, "  ")

	if len(warnings) == 0 {
		fmt.Println("Warnings:")
		fmt.Println()
		fmt.Println("  none")
	} else {
		fmt.Println("Warnings:")
		fmt.Println()
		for _, warning := range warnings {
			fmt.Printf("  - %s\n", warning.Message)
			for i := 0; i+1 < len(warning.Attrs); i += 2 {
				key, ok := warning.Attrs[i].(string)
				if !ok || key == "hint" {
					continue
				}
				fmt.Printf("      %s: %s\n", key, formatSecurityValue(warning.Attrs[i+1]))
			}
			for i := 0; i+1 < len(warning.Attrs); i += 2 {
				key, ok := warning.Attrs[i].(string)
				if ok && key == "hint" {
					fmt.Printf("      hint: %s\n", formatSecurityValue(warning.Attrs[i+1]))
				}
			}
		}
	}

	fmt.Println()
	fmt.Println("Recommended security defaults:")
	fmt.Println()
	if len(recommended) == 0 {
		fmt.Println("  none")
	} else {
		printRecommendedSecurityDefaults(recommended)
	}
	fmt.Println()

	if !isInteractiveTerminal() {
		fmt.Println("Interactive restore skipped because stdin/stdout is not a terminal.")
		return
	}

	if !promptRestoreDefaults() {
		fmt.Println("No changes made.")
		return
	}

	configPath, changed, err := restoreSecurityDefaults()
	if err != nil {
		fmt.Printf("Error restoring defaults: %v\n", err)
		os.Exit(1)
	}
	if !changed {
		fmt.Printf("Security defaults already match %s\n", configPath)
		return
	}

	fmt.Printf("Security defaults restored in %s\n", configPath)
	fmt.Println("Restart PinchTab to apply file-based changes.")
}

func formatSecurityValue(value any) string {
	switch v := value.(type) {
	case []string:
		return strings.Join(v, ", ")
	default:
		return fmt.Sprint(v)
	}
}

func securityUsage() {
	fmt.Println("Usage: pinchtab security")
	fmt.Println()
	fmt.Println("Shows runtime security posture and offers to restore recommended security defaults.")
}

func printRecommendedSecurityDefaults(lines []string) {
	for _, line := range lines {
		fmt.Printf("  - %s\n", line)
	}
}

func recommendedSecurityDefaultLines(cfg *config.RuntimeConfig) []string {
	posture := assessSecurityPosture(cfg)
	ordered := []string{
		"server.bind = 127.0.0.1",
		"security.allowEvaluate = false",
		"security.allowMacro = false",
		"security.allowScreencast = false",
		"security.allowDownload = false",
		"security.allowUpload = false",
		"security.attach.enabled = false",
		"security.attach.allowHosts = 127.0.0.1,localhost,::1",
		"security.attach.allowSchemes = ws,wss",
		"security.idpi.enabled = true",
		"security.idpi.allowedDomains = 127.0.0.1,localhost,::1",
		"security.idpi.strictMode = true",
		"security.idpi.scanContent = true",
		"security.idpi.wrapContent = true",
	}
	needed := make(map[string]bool, len(ordered))

	for _, check := range posture.Checks {
		if check.Passed {
			continue
		}
		switch check.ID {
		case "bind_loopback":
			needed["server.bind = 127.0.0.1"] = true
		case "sensitive_endpoints_disabled":
			needed["security.allowEvaluate = false"] = true
			needed["security.allowMacro = false"] = true
			needed["security.allowScreencast = false"] = true
			needed["security.allowDownload = false"] = true
			needed["security.allowUpload = false"] = true
		case "attach_disabled":
			needed["security.attach.enabled = false"] = true
			needed["security.attach.allowHosts = 127.0.0.1,localhost,::1"] = true
			needed["security.attach.allowSchemes = ws,wss"] = true
		case "attach_local_only":
			needed["security.attach.allowHosts = 127.0.0.1,localhost,::1"] = true
			needed["security.attach.allowSchemes = ws,wss"] = true
		case "idpi_whitelist_scoped", "idpi_strict_mode", "idpi_content_protection":
			needed["security.idpi.enabled = true"] = true
			needed["security.idpi.allowedDomains = 127.0.0.1,localhost,::1"] = true
			needed["security.idpi.strictMode = true"] = true
			needed["security.idpi.scanContent = true"] = true
			needed["security.idpi.wrapContent = true"] = true
		}
	}

	lines := make([]string, 0, len(needed))
	for _, line := range ordered {
		if needed[line] {
			lines = append(lines, line)
		}
	}
	return lines
}

func promptRestoreDefaults() bool {
	fmt.Print("Restore recommended security defaults in config? (y/N): ")
	reader := bufio.NewReader(os.Stdin)
	response, err := reader.ReadString('\n')
	if err != nil && strings.TrimSpace(response) == "" {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(response)) {
	case "y", "yes":
		return true
	default:
		return false
	}
}

func isInteractiveTerminal() bool {
	in, err := os.Stdin.Stat()
	if err != nil || (in.Mode()&os.ModeCharDevice) == 0 {
		return false
	}
	out, err := os.Stdout.Stat()
	if err != nil || (out.Mode()&os.ModeCharDevice) == 0 {
		return false
	}
	return true
}

func restoreSecurityDefaults() (string, bool, error) {
	fc, configPath, err := config.LoadFileConfig()
	if err != nil {
		return "", false, err
	}
	before := securityDefaultsSnapshot(fc)
	applyRecommendedSecurityDefaults(fc)
	after := securityDefaultsSnapshot(fc)
	if reflect.DeepEqual(before, after) {
		return configPath, false, nil
	}
	if err := config.SaveFileConfig(fc, configPath); err != nil {
		return "", false, err
	}
	return configPath, true, nil
}

func applyRecommendedSecurityDefaults(fc *config.FileConfig) {
	defaults := config.DefaultFileConfig()
	if fc == nil {
		return
	}
	fc.Server.Bind = defaults.Server.Bind
	if strings.TrimSpace(fc.Server.Token) == "" {
		token, err := config.GenerateAuthToken()
		if err == nil {
			fc.Server.Token = token
		}
	}
	fc.Security = defaults.Security
}

type securityDefaultsState struct {
	Bind     string
	Token    string
	Security config.SecurityConfig
}

func securityDefaultsSnapshot(fc *config.FileConfig) securityDefaultsState {
	if fc == nil {
		return securityDefaultsState{}
	}
	return securityDefaultsState{
		Bind:     fc.Server.Bind,
		Token:    fc.Server.Token,
		Security: fc.Security,
	}
}
