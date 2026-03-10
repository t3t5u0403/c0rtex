package orchestrator

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"

	"github.com/pinchtab/pinchtab/internal/handlers"
	"github.com/pinchtab/pinchtab/internal/web"
)

// proxyTabRequest is a generic handler that proxies requests to the instance
// that owns the tab specified in the path. Works for any /tabs/{id}/* route.
//
// Uses the instance Manager's Locator for O(1) cached lookups, falling back
// to the legacy O(n×m) bridge query on cache miss.
func (o *Orchestrator) proxyTabRequest(w http.ResponseWriter, r *http.Request) {
	tabID := r.PathValue("id")
	if tabID == "" {
		web.Error(w, 400, fmt.Errorf("tab id required"))
		return
	}

	// Fast path: Locator cache hit
	if o.instanceMgr != nil {
		if inst, err := o.instanceMgr.FindInstanceByTabID(tabID); err == nil {
			targetURL := &url.URL{
				Scheme:   "http",
				Host:     net.JoinHostPort("localhost", inst.Port),
				Path:     r.URL.Path,
				RawQuery: r.URL.RawQuery,
			}
			o.proxyToURL(w, r, targetURL)
			return
		}
	}

	// Slow path: legacy lookup
	inst, err := o.findRunningInstanceByTabID(tabID)
	if err != nil {
		web.Error(w, 404, err)
		return
	}

	// Cache for future O(1) lookups
	if o.instanceMgr != nil {
		o.instanceMgr.Locator.Register(tabID, inst.ID)
	}

	targetURL := &url.URL{
		Scheme:   "http",
		Host:     net.JoinHostPort("localhost", inst.Port),
		Path:     r.URL.Path,
		RawQuery: r.URL.RawQuery,
	}
	o.proxyToURL(w, r, targetURL)
}

// proxyToInstance proxies a request to a specific instance by ID in the path.
func (o *Orchestrator) proxyToInstance(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")

	o.mu.RLock()
	inst, ok := o.instances[id]
	o.mu.RUnlock()

	if !ok {
		web.Error(w, 404, fmt.Errorf("instance %q not found", id))
		return
	}

	if inst.Status != "running" {
		web.Error(w, 503, fmt.Errorf("instance %q is not running (status: %s)", id, inst.Status))
		return
	}

	targetPath := r.URL.Path
	if len(targetPath) > len("/instances/"+id) {
		targetPath = targetPath[len("/instances/"+id):]
	} else {
		targetPath = ""
	}

	targetURL := &url.URL{
		Scheme:   "http",
		Host:     net.JoinHostPort("localhost", inst.Port),
		Path:     targetPath,
		RawQuery: r.URL.RawQuery,
	}
	o.proxyToURL(w, r, targetURL)
}

// proxyToURL proxies an HTTP request to the given target URL.
func (o *Orchestrator) proxyToURL(w http.ResponseWriter, r *http.Request, targetURL *url.URL) {
	if targetURL.Hostname() != "localhost" {
		web.Error(w, 400, fmt.Errorf("invalid proxy target: only localhost allowed"))
		return
	}

	proxyReq, err := http.NewRequest(r.Method, targetURL.String(), r.Body)
	if err != nil {
		web.Error(w, 500, fmt.Errorf("failed to create proxy request: %w", err))
		return
	}

	for key, values := range r.Header {
		switch key {
		case "Host", "Connection", "Keep-Alive", "Proxy-Authenticate",
			"Proxy-Authorization", "Te", "Trailers", "Transfer-Encoding", "Upgrade":
		default:
			for _, value := range values {
				proxyReq.Header.Add(key, value)
			}
		}
	}

	resp, err := o.client.Do(proxyReq)
	if err != nil {
		web.Error(w, 502, fmt.Errorf("failed to proxy to instance: %w", err))
		return
	}
	defer func() { _ = resp.Body.Close() }()

	for key, values := range resp.Header {
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}

	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

// findRunningInstanceByTabID finds the instance that owns the given tab.
func (o *Orchestrator) findRunningInstanceByTabID(tabID string) (*InstanceInternal, error) {
	o.mu.RLock()
	instances := make([]*InstanceInternal, 0, len(o.instances))
	for _, inst := range o.instances {
		if inst.Status == "running" && instanceIsActive(inst) {
			instances = append(instances, inst)
		}
	}
	o.mu.RUnlock()

	for _, inst := range instances {
		tabs, err := o.fetchTabs(inst.URL)
		if err != nil {
			continue
		}
		for _, tab := range tabs {
			if tab.ID == tabID || o.idMgr.TabIDFromCDPTarget(tab.ID) == tabID {
				return inst, nil
			}
		}
	}
	return nil, fmt.Errorf("tab %q not found", tabID)
}

func (o *Orchestrator) handleProxyScreencast(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")

	o.mu.RLock()
	inst, ok := o.instances[id]
	o.mu.RUnlock()
	if !ok || inst.Status != "running" {
		web.Error(w, 404, fmt.Errorf("instance not found or not running"))
		return
	}

	// Build target URL preserving all query params (tabId, quality, maxWidth, fps)
	targetURL := fmt.Sprintf("http://localhost:%s/screencast?%s", inst.Port, r.URL.RawQuery)

	// Inject child auth token if configured
	if o.childAuthToken != "" {
		r.Header.Set("Authorization", "Bearer "+o.childAuthToken)
	}

	// Use WebSocket proxy for proper upgrade
	handlers.ProxyWebSocket(w, r, targetURL)
}

// classifyLaunchError returns appropriate HTTP status code for launch errors.
func classifyLaunchError(err error) int {
	msg := err.Error()
	if strings.Contains(msg, "cannot contain") || strings.Contains(msg, "cannot be empty") {
		return 400 // Bad Request - validation error
	}
	if strings.Contains(msg, "already") || strings.Contains(msg, "in use") {
		return 409 // Conflict - resource already exists
	}
	return 500 // Internal Server Error
}
