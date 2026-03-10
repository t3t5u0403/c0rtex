# Click

Click an element by ref from a previous snapshot.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"click","ref":"e5"}'
# CLI Alternative
pinchtab click e5
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

Notes:

- element refs come from `/snapshot`
- `--wait-nav` exists on the top-level CLI command

## Related Pages

- [Snapshot](./snapshot.md)
- [Navigate](./navigate.md)

