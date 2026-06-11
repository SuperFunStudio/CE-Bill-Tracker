# Embedding the Bill Tracker (Squarespace, etc.)

The Bill Explorer is available as a chrome-free, iframe-friendly page on the
**dashboard's own domain** (the Firebase-hosted Next.js app — *not* the
Squarespace site):

```
https://ce-bill-tracker.web.app/embed/
```

> ⚠️ The `src` must point at the dashboard's Firebase URL above. Do **not** use
> your Squarespace domain (e.g. `kennyarnold.com`) — Squarespace doesn't serve
> this page, so it would 404. Squarespace is only the *host* page that embeds the
> iframe.

It has no top nav and no fixed page height, so it drops cleanly into any host
page. It renders the same searchable/filterable bill table as the homepage and
opens the per-bill detail panel on click.

## Quick start (Squarespace)

1. Edit the Squarespace page where you want the tracker (e.g. `/tools`) →
   **Add Block** → **Code**.
2. Paste the snippet below as-is — the `src` already points at the live
   dashboard.
3. Save. The iframe auto-resizes to its content (no inner scrollbar).

```html
<div id="bill-tracker-embed" style="width:100%">
  <iframe
    src="https://ce-bill-tracker.web.app/embed/"
    title="Circularity Legislation Tracker"
    style="width:100%;border:0;height:900px;display:block"
    loading="lazy"
    referrerpolicy="no-referrer-when-downgrade"
  ></iframe>
</div>
<script>
  // Auto-resize the iframe to match its content height.
  window.addEventListener('message', function (e) {
    var d = e.data || {};
    if (d.type === 'signalscout-embed-height') {
      var f = document.querySelector('#bill-tracker-embed iframe');
      if (f && d.height) f.style.height = d.height + 'px';
    }
  });
</script>
```

If you'd rather keep a fixed height with an internal scrollbar, drop the
`<script>` block and set `height` on the iframe to whatever you like.

## Configuration (URL query params)

Append these to the `src` URL to scope or restyle the embed. The same static
build powers every variant — no rebuild needed.

| Param        | Example                  | Effect                                             |
|--------------|--------------------------|----------------------------------------------------|
| `theme`      | `?theme=dark`            | Force dark mode (default: light)                   |
| `state`      | `?state=CA`              | Preset the State filter (visitor can still change) |
| `status`     | `?status=enacted`        | Preset the Status filter                           |
| `instrument` | `?instrument=epr`        | Preset the Instrument filter                       |
| `material`   | `?material=plastic_packaging` | Preset the Material filter                    |
| `search`     | `?search=foam`           | Preset the search box                              |
| `filters`    | `?filters=0`             | Hide the filter bar (locked, read-only table)      |
| `heading`    | `?heading=0`             | Hide the "N bills" heading + full-tracker link     |
| `rows`       | `?rows=10`               | Rows per page (default 8)                          |

Combine with `&`, e.g. a locked California-only dark view:

```
https://ce-bill-tracker.web.app/embed/?state=CA&filters=0&theme=dark&rows=10
```

## Notes

- **Host-site iframe headers.** Most hosts (incl. Squarespace) embed via iframe
  fine. If the dashboard is ever served with `X-Frame-Options: DENY` or a CSP
  `frame-ancestors` rule at the CDN/hosting layer, embedding will be blocked —
  the static export itself sets no such header. Allow your Squarespace domain in
  `frame-ancestors` if you lock this down.
- **API origin.** The embed fetches from the API base baked in at build time
  (`NEXT_PUBLIC_API_BASE_URL`). That API must allow CORS from the browser, which
  it already does for the main dashboard.
