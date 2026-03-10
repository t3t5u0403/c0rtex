# Health

Check whether the current browser context is available and how many tabs are open.

```bash
curl http://localhost:9867/health
# CLI Alternative
pinchtab health
# Response
{
  "status": "ok",
  "tabs": 1
}
```

Notes:

- this is a shorthand route for the current browser context
- in error cases it returns `503` with `status: "error"`

## Related Pages

- [Tabs](./tabs.md)
- [Navigate](./navigate.md)

