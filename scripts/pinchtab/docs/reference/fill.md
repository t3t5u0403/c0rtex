# Fill

Set an input value directly without relying on the same event sequence as `type`.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"fill","ref":"e8","text":"ada@example.com"}'
# CLI Alternative
pinchtab fill e8 "ada@example.com"
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

Notes:

- the top-level CLI also accepts a selector form: `pinchtab fill 'input[name=email]' "ada@example.com"`
- for the raw HTTP action endpoint, selectors use `selector`, not `ref`

## Related Pages

- [Type](./type.md)
- [Snapshot](./snapshot.md)

