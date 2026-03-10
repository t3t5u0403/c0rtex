# Type

Type text into an element, sending key events as the text is entered.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"type","ref":"e8","text":"Ada Lovelace"}'
# CLI Alternative
pinchtab type e8 "Ada Lovelace"
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

Notes:

- use `fill` when you want to set the value more directly
- top-level `type` expects a ref, not a CSS selector

## Related Pages

- [Fill](./fill.md)
- [Snapshot](./snapshot.md)

