# Screenshot

Capture the current page as an image.

```bash
curl "http://localhost:9867/screenshot?output=file"
# CLI Alternative
pinchtab ss -o page.jpg
# Response
{
  "path": "/path/to/state/screenshots/screenshot-20260308-120001.jpg",
  "size": 34567,
  "format": "jpeg",
  "timestamp": "20260308-120001"
}
```

Useful flags:

- CLI: `-o`, `-q`, `--tab`
- API query: `quality`, `raw`, `output=file`, `tabId`

## Related Pages

- [Snapshot](./snapshot.md)
- [PDF](./pdf.md)

