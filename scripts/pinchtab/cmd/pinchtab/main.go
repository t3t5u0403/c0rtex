package main

import (
	"fmt"
	"os"

	"github.com/pinchtab/pinchtab/internal/config"
)

var version = "dev"

func startupMode(args []string) (string, bool) {
	if len(args) <= 1 {
		return "server", true
	}
	switch args[1] {
	case "server":
		return "server", true
	case "bridge":
		return "bridge", true
	}
	return "", false
}

func main() {
	cfg := config.Load()

	if len(os.Args) > 1 && (os.Args[1] == "--version" || os.Args[1] == "-v") {
		fmt.Printf("pinchtab %s\n", version)
		os.Exit(0)
	}

	if len(os.Args) > 1 && (os.Args[1] == "help" || os.Args[1] == "--help" || os.Args[1] == "-h") {
		printHelp()
		os.Exit(0)
	}

	if len(os.Args) > 1 && os.Args[1] == "config" {
		config.HandleConfigCommand(cfg)
		os.Exit(0)
	}

	if len(os.Args) > 1 && os.Args[1] == "connect" {
		handleConnectCommand(cfg)
		os.Exit(0)
	}

	if len(os.Args) > 1 && os.Args[1] == "security" {
		if len(os.Args) > 2 && (os.Args[2] == "help" || os.Args[2] == "--help" || os.Args[2] == "-h") {
			securityUsage()
			os.Exit(0)
		}
		handleSecurityCommand(cfg)
		os.Exit(0)
	}

	// CLI commands
	if len(os.Args) > 1 && isCLICommand(os.Args[1]) {
		runCLI(cfg)
		return
	}

	mode, ok := startupMode(os.Args)
	if !ok {
		fmt.Fprintf(os.Stderr, "unknown command: %s\n\n", os.Args[1])
		printHelp()
		os.Exit(1)
	}

	switch mode {
	case "bridge":
		runBridgeServer(cfg)
	case "server":
		runDashboard(cfg)
	default:
		runDashboard(cfg)
	}
}
