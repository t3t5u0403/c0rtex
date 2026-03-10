# Profiles

Profiles are browser user data directories. They hold cookies, local storage, history, and other durable browser state.

In PinchTab:

- profiles exist even when no instance is running
- one profile can have at most one active managed instance at a time
- profile IDs and names are both useful, but some endpoints require the profile ID specifically

## List Profiles

```bash
curl http://localhost:9867/profiles
# CLI Alternative
pinchtab profiles
# Response
[
  {
    "id": "278be873adeb",
    "name": "work",
    "created": "2026-02-27T20:37:13.599055326Z",
    "diskUsage": 534952089,
    "sizeMB": 510.17,
    "running": false,
    "source": "created",
    "useWhen": "Use for work accounts",
    "description": ""
  }
]
```

Notes:

- `GET /profiles` excludes temporary auto-generated instance profiles by default
- use `GET /profiles?all=true` to include temporary profiles
- `pinchtab profiles` exists, but the HTTP API is the more reliable source of truth for structured output

## Get One Profile

```bash
curl http://localhost:9867/profiles/278be873adeb
# Response
{
  "id": "278be873adeb",
  "name": "work",
  "path": "/path/to/profiles/work",
  "pathExists": true,
  "created": "2026-02-27T20:37:13.599055326Z",
  "diskUsage": 534952089,
  "sizeMB": 510.17,
  "source": "created",
  "chromeProfileName": "Your Chrome",
  "accountEmail": "admin@example.com",
  "accountName": "Luigi",
  "hasAccount": true,
  "useWhen": "Use for work accounts",
  "description": ""
}
```

`GET /profiles/{id}` accepts either the profile ID or the profile name.

## Create A Profile

```bash
curl -X POST http://localhost:9867/profiles \
  -H "Content-Type: application/json" \
  -d '{"name":"scraping-profile","description":"Used for scraping","useWhen":"Use for ecommerce scraping"}'
# Response
{
  "status": "created",
  "id": "0f32ae81e4a1",
  "name": "scraping-profile"
}
```

There is no `pinchtab profile create` CLI command today.

## Update A Profile

```bash
curl -X PATCH http://localhost:9867/profiles/278be873adeb \
  -H "Content-Type: application/json" \
  -d '{"description":"Updated description","useWhen":"Updated usage note"}'
# Response
{
  "status": "updated",
  "id": "278be873adeb",
  "name": "work"
}
```

You can also rename the profile:

```bash
curl -X PATCH http://localhost:9867/profiles/278be873adeb \
  -H "Content-Type: application/json" \
  -d '{"name":"work-renamed"}'
```

Important:

- `PATCH /profiles/{id}` requires the profile ID
- using the profile name in that path returns an error
- a rename changes the generated profile ID because IDs are derived from the name

## Delete A Profile

```bash
curl -X DELETE http://localhost:9867/profiles/278be873adeb
# Response
{
  "status": "deleted",
  "id": "278be873adeb",
  "name": "work"
}
```

`DELETE /profiles/{id}` also requires the profile ID.

## Start Or Stop By Profile

Start the active instance for a profile:

```bash
curl -X POST http://localhost:9867/profiles/278be873adeb/start \
  -H "Content-Type: application/json" \
  -d '{"headless":true}'
# Response
{
  "id": "inst_ea2e747f",
  "profileId": "278be873adeb",
  "profileName": "work",
  "port": "9868",
  "headless": true,
  "status": "starting"
}
```

Stop the active instance for a profile:

```bash
curl -X POST http://localhost:9867/profiles/278be873adeb/stop
# Response
{
  "status": "stopped",
  "id": "278be873adeb",
  "name": "work"
}
```

For these orchestrator routes, the path can be a profile ID or profile name.

## Check Whether A Profile Has A Running Instance

```bash
curl http://localhost:9867/profiles/278be873adeb/instance
# Response
{
  "name": "work",
  "running": true,
  "status": "running",
  "port": "9868",
  "id": "inst_ea2e747f"
}
```

## Additional Profile Operations

### Reset A Profile

```bash
curl -X POST http://localhost:9867/profiles/278be873adeb/reset
```

This route requires the profile ID.

### Import A Profile

```bash
curl -X POST http://localhost:9867/profiles/import \
  -H "Content-Type: application/json" \
  -d '{"name":"imported-profile","sourcePath":"/path/to/existing/profile"}'
```

### Get Logs

```bash
curl http://localhost:9867/profiles/278be873adeb/logs
curl 'http://localhost:9867/profiles/work/logs?limit=50'
```

`logs` accepts either the profile ID or the profile name.

### Get Analytics

```bash
curl http://localhost:9867/profiles/278be873adeb/analytics
curl http://localhost:9867/profiles/work/analytics
```

`analytics` also accepts either the profile ID or the profile name.

## Related Pages

- [Instances](./instances.md)
- [Tabs](./tabs.md)
- [Config](./config.md)
