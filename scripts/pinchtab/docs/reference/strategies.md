# Strategies And Allocation

PinchTab has two separate multi-instance controls:

- `multiInstance.strategy`
- `multiInstance.allocationPolicy`

They solve different problems:

```text
strategy          = what routes PinchTab exposes and how shorthand requests behave
allocationPolicy  = which running instance gets picked when PinchTab must choose one
```

## Strategy

Valid strategies in the current implementation:

- `simple`
- `explicit`
- `simple-autorestart`

### `simple`

`simple` is the default.

Behavior:

- registers the full orchestrator API
- keeps shorthand routes such as `/snapshot`, `/text`, `/navigate`, and `/tabs`
- if a shorthand request arrives and no instance is running, PinchTab auto-launches one managed instance and waits for it to become healthy

Best fit:

- local development
- single-user automation
- “just make the browser service available” setups

### `explicit`

`explicit` also exposes the orchestrator API and shorthand routes, but it does not auto-launch on shorthand requests.

Behavior:

- you start instances explicitly with `/instances/start`, `/instances/launch`, or `/profiles/{id}/start`
- shorthand routes proxy to the first running instance only if one already exists
- if nothing is running, shorthand routes return an error instead of launching a browser for you

Best fit:

- controlled multi-instance environments
- agents that should name instances deliberately
- deployments where hidden auto-launch would be surprising

### `simple-autorestart`

`simple-autorestart` behaves like a managed single-instance service with recovery.

Behavior:

- launches one managed instance when the strategy starts
- exposes the same shorthand routes as `simple`
- watches that managed instance and tries to restart it after unexpected exits
- exposes `GET /autorestart/status` for restart state

Best fit:

- kiosk or appliance-style setups
- unattended local services
- environments where one browser should come back after a crash

## Allocation Policy

Valid policies in the current implementation:

- `fcfs`
- `round_robin`
- `random`

Allocation policy matters only when PinchTab has multiple eligible running instances and needs to choose one. If your request already targets `/instances/{id}/...`, no allocation policy is involved for that request.

### `fcfs`

First running candidate wins.

Best fit:

- predictable behavior
- simplest operational model
- “always use the earliest running instance” workflows

### `round_robin`

Candidates are selected in rotation.

Best fit:

- light balancing across a stable pool
- repeated shorthand-style traffic where you want even distribution over time

### `random`

PinchTab picks a random eligible candidate.

Best fit:

- looser balancing
- experiments where deterministic ordering is not important

## Example Config

```json
{
  "multiInstance": {
    "strategy": "explicit",
    "allocationPolicy": "round_robin",
    "instancePortStart": 9868,
    "instancePortEnd": 9968
  }
}
```

## Recommended Defaults

### Simple Local Service

```json
{
  "multiInstance": {
    "strategy": "simple",
    "allocationPolicy": "fcfs"
  }
}
```

Use this when you want shorthand routes to feel like a single local browser service.

### Explicit Orchestration

```json
{
  "multiInstance": {
    "strategy": "explicit",
    "allocationPolicy": "round_robin"
  }
}
```

Use this when your client is instance-aware and you want to control lifecycle directly.

### Self-Healing Single Service

```json
{
  "multiInstance": {
    "strategy": "simple-autorestart",
    "allocationPolicy": "fcfs"
  }
}
```

Use this when one managed browser should stay available and recover after crashes.

## Decision Rule

```text
simple              = easiest default, auto-launches on shorthand traffic
explicit            = most control, no shorthand auto-launch
simple-autorestart  = one managed browser with crash recovery

fcfs                = deterministic
round_robin         = balanced rotation
random              = loose distribution
```

