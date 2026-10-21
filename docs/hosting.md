# Hosting and costs

## Today: $0/month

| Piece | Where | Cost |
|---|---|---|
| Daily data pull | GitHub Actions (`.github/workflows/update.yml`) | free for public repos |
| Raw archive | `data` branch of this repo | free |
| Website + JSON + SQLite | GitHub Pages | free |
| SQL in the browser | Datasette Lite (runs client-side) | free |

Setup after pushing to GitHub:

1. Settings → Pages → Source: **GitHub Actions**.
2. Actions → "Update data and site" → **Run workflow** once. It then runs daily.
3. Optional: add a `CENSUS_API_KEY` repository secret when the Census adapter lands
   (free key from api.census.gov).
4. Optional custom domain: Settings → Pages → Custom domain (about $10–15/year for the domain).

Limits to watch: GitHub recommends keeping repositories under a few GB. The archive is
about 1 MB per few hundred documents. Several topics can run for years before this
matters.

## Next steps as it grows

| Need | Option | Rough cost |
|---|---|---|
| Archive outgrows git (full texts, PDFs) | Cloudflare R2 (no egress fees) | free up to 10 GB, then ~$0.015/GB-month |
| Faster global site, analytics without cookies | Cloudflare Pages | free |
| Live SQL/JSON API | Datasette on Fly.io or Google Cloud Run (scales to zero) | ~$0–5/month |
| MCP server for AI agents | Same container as the API, read-only over the SQLite file | included |
| LLM extraction/narratives | Batch jobs with prompt caching, only on new documents | a few $/month at current volume |
| Chat interface | Only once the verified layer exists; rate-limited, possibly bring-your-own-key | varies |

## Getting it in front of people who'd use it

- **Reporters:** the "Copy citation" button and SQLite download are built for them.
  Trade, politics, and business desks in Canada are the first audience for this topic.
  Concrete asks: is the citation format usable, and which source is missing?
- **Researchers and data people:** the SQLite file + Datasette Lite link, and the
  `data` branch as a reproducible archive.
- **Developers and agents:** JSON exports now, an API + MCP server next.
- **Launch post:** a screen recording of the chart → click a tick → primary source
  flow works better than a description. Keep the repo link in the first post.
