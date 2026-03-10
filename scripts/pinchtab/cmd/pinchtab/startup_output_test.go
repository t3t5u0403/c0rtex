package main

import "testing"

func TestSecurityLevelColor(t *testing.T) {
	tests := []struct {
		level string
		want  string
	}{
		{level: "LOCKED", want: ansiGreen},
		{level: "GUARDED", want: ansiYellow},
		{level: "ELEVATED", want: ansiRed},
		{level: "EXPOSED", want: ansiRed},
		{level: "UNKNOWN", want: ansiRed},
	}

	for _, tt := range tests {
		if got := securityLevelColor(tt.level); got != tt.want {
			t.Fatalf("securityLevelColor(%q) = %q, want %q", tt.level, got, tt.want)
		}
	}
}
