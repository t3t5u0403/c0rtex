package bridge

import (
	"strings"

	"github.com/chromedp/chromedp"
	"github.com/shirou/gopsutil/v4/process"
)

// MemoryMetrics holds Chrome memory statistics
type MemoryMetrics struct {
	// OS-level memory (real RAM usage)
	MemoryMB float64 `json:"memoryMB"` // Total RSS across renderer processes

	// Legacy JS-heap fields (for backward compat, now estimated)
	JSHeapUsedMB  float64 `json:"jsHeapUsedMB"`
	JSHeapTotalMB float64 `json:"jsHeapTotalMB"`

	// Process counts
	Renderers int `json:"renderers"` // Number of renderer processes (≈ tabs)

	// Legacy fields (set to 0, kept for API compat)
	Documents int64 `json:"documents"`
	Frames    int64 `json:"frames"`
	Nodes     int64 `json:"nodes"`
	Listeners int64 `json:"listeners"`
}

// GetMemoryMetrics retrieves memory metrics for a specific tab
// Now uses OS-level memory instead of per-tab CDP calls
func (b *Bridge) GetMemoryMetrics(tabID string) (*MemoryMetrics, error) {
	// For single tab, return aggregated (we can't map tab→PID reliably)
	return b.GetAggregatedMemoryMetrics()
}

// GetBrowserMemoryMetrics retrieves memory metrics for the entire browser
func (b *Bridge) GetBrowserMemoryMetrics() (*MemoryMetrics, error) {
	return b.GetAggregatedMemoryMetrics()
}

// GetAggregatedMemoryMetrics returns real OS memory usage across all Chrome processes
// Uses process tree approach: walks the browser process and its children
func (b *Bridge) GetAggregatedMemoryMetrics() (*MemoryMetrics, error) {
	if b.BrowserCtx == nil {
		return nil, nil
	}

	// Always use process tree approach - it's more reliable for isolating this instance
	return b.getMemoryViaProcessTree()
}

// getMemoryViaProcessTree is a fallback that walks the browser process tree
func (b *Bridge) getMemoryViaProcessTree() (*MemoryMetrics, error) {
	result := &MemoryMetrics{}

	// Get browser PID from chromedp
	browser := chromedp.FromContext(b.BrowserCtx)
	if browser == nil || browser.Browser == nil {
		return result, nil
	}

	proc := browser.Browser.Process()
	if proc == nil {
		return result, nil
	}

	mainPID := int32(proc.Pid)
	p, err := process.NewProcess(mainPID)
	if err != nil {
		return result, err
	}

	// Get all children (recursive)
	children, err := p.Children()
	if err != nil {
		// Just count main process
		mem, _ := getProcessMemory(mainPID)
		result.MemoryMB = float64(mem) / (1024 * 1024)
		return result, nil
	}

	var totalMem uint64
	rendererCount := 0

	// Add main process
	mem, _ := getProcessMemory(mainPID)
	totalMem += mem

	// Add children
	for _, child := range children {
		cmdline, _ := child.Cmdline()
		// Filter for renderer processes
		if containsRenderer(cmdline) {
			rendererCount++
		}
		childMem, _ := getProcessMemory(child.Pid)
		totalMem += childMem
	}

	result.MemoryMB = float64(totalMem) / (1024 * 1024)
	result.Renderers = rendererCount
	result.JSHeapUsedMB = result.MemoryMB * 0.4
	result.JSHeapTotalMB = result.MemoryMB * 0.5

	return result, nil
}

// getProcessMemory returns RSS memory in bytes for a process
func getProcessMemory(pid int32) (uint64, error) {
	p, err := process.NewProcess(pid)
	if err != nil {
		return 0, err
	}

	mem, err := p.MemoryInfo()
	if err != nil {
		return 0, err
	}

	// RSS is the resident set size (actual RAM used)
	return mem.RSS, nil
}

// containsRenderer checks if cmdline indicates a renderer process
func containsRenderer(cmdline string) bool {
	return strings.Contains(cmdline, "--type=renderer") || strings.Contains(cmdline, "--type=tab")
}
