# Scroll

Scroll the current tab by direction or pixel amount.

```bash
curl -X POST http://localhost:9867/action \
  -H "Content-Type: application/json" \
  -d '{"kind":"scroll","direction":"down"}'
# CLI Alternative
pinchtab scroll down
# Response
{
  "success": true,
  "result": {
    "success": true
  }
}
```

Notes:

- the top-level CLI also accepts a pixel value such as `pinchtab scroll 800`
- the raw API can also use `scrollY`

## Related Pages

- [Snapshot](./snapshot.md)
- [Text](./text.md)

