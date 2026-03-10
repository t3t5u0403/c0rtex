# Focus

Move focus to an element by ref.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"focus","ref":"e8"}'
# CLI Alternative
pinchtab focus e8
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

This is useful before keyboard-only flows such as `press Enter` or `type`.

## Related Pages

- [Press](./press.md)
- [Type](./type.md)
