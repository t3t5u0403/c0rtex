# Docker Deployment

PinchTab can run in Docker with a mounted data volume for config, profiles, and state. The safest way to configure the current implementation is to mount a `config.json` file and point `PINCHTAB_CONFIG` at it.

## Quick Start

Build the image from this repository:

```bash
docker build -t pinchtab .
```

Create a local data directory with config:

```text
docker-data/
└── config.json
```

Example `docker-data/config.json`:

```json
{
  "server": {
    "bind": "0.0.0.0",
    "port": "9867",
    "stateDir": "/data/state"
  },
  "profiles": {
    "baseDir": "/data/profiles",
    "defaultProfile": "default"
  },
  "instanceDefaults": {
    "mode": "headless",
    "noRestore": true
  }
}
```

Run the container:

```bash
docker run -d \
  --name pinchtab \
  -p 9867:9867 \
  -v "$PWD/docker-data:/data" \
  -e PINCHTAB_CONFIG=/data/config.json \
  --shm-size=2g \
  --security-opt seccomp=unconfined \
  pinchtab
```

Check it:

```bash
curl http://localhost:9867/health
curl http://localhost:9867/instances
```

## What To Persist

If you want data to survive container restarts, persist:

- the config file
- the profile directory
- the state directory

Without a mounted volume, profiles and saved session state are ephemeral.

## Runtime Configuration

For current runtime overrides, rely on:

- `PINCHTAB_CONFIG`
- `PINCHTAB_BIND`
- `PINCHTAB_PORT`
- `PINCHTAB_TOKEN`
- `CHROME_BIN`

Everything else should go in `config.json`.

In the bundled image, you usually do not need to set `CHROME_BIN` manually unless you are replacing the browser binary.

## Compose

The repository includes a `docker-compose.yml`, but the stable configuration pattern is still:

1. mount a persistent data directory
2. point `PINCHTAB_CONFIG` at `/data/config.json`
3. keep behavior settings in that file

If you expose PinchTab beyond localhost, set an auth token and put it behind TLS or a trusted reverse proxy.

## Resource Notes

Chrome in containers usually needs:

- larger shared memory, such as `--shm-size=2g`
- a relaxed seccomp profile such as `seccomp=unconfined`
- enough RAM for your tab count and workload

For heavier scraping or testing workloads, also consider:

- lowering `instanceDefaults.maxTabs`
- setting block options like `blockImages` in config
- running multiple smaller containers instead of one oversized browser

## Multi-Instance In Containers

You can run orchestrator mode inside one container and start managed instances from the API, but many teams prefer one browser service per container because:

- lifecycle is simpler
- container-level resource limits are clearer
- restart behavior is easier to reason about

Choose based on whether you want container-level isolation or PinchTab-managed multi-instance orchestration.
