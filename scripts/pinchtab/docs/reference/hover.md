# Hover

Move the pointer over an element by ref.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"hover","ref":"e5"}'
# CLI Alternative
pinchtab hover e5
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

Use this when menus or tooltips appear only after hover.

## Related Pages

- [Click](./click.md)
- [Snapshot](./snapshot.md)

