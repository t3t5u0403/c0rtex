# Build stage
FROM golang:1.26-alpine AS builder
RUN apk add --no-cache git
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -ldflags="-s -w" -o pinchtab ./cmd/pinchtab

# Runtime stage
FROM alpine:latest

LABEL org.opencontainers.image.source="https://github.com/pinchtab/pinchtab"
LABEL org.opencontainers.image.description="High-performance browser automation bridge"

# Install Chromium and dependencies
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    dumb-init

# Create non-root user and state directory
RUN adduser -D -g '' pinchtab && \
    mkdir -p /data && \
    chown pinchtab:pinchtab /data

# Copy binary from builder
COPY --from=builder /build/pinchtab /usr/local/bin/pinchtab

# Switch to non-root user
USER pinchtab
WORKDIR /data

# Environment variables
ENV BRIDGE_BIND=0.0.0.0 \
    BRIDGE_PORT=9867 \
    BRIDGE_HEADLESS=true \
    BRIDGE_STATE_DIR=/data \
    BRIDGE_PROFILE=/data/chrome-profile \
    CHROME_BINARY=/usr/bin/chromium-browser \
    CHROME_FLAGS="--no-sandbox --disable-gpu"

# Expose port
EXPOSE 9867

# Use dumb-init to properly handle signals
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# Run pinchtab
CMD ["pinchtab"]