# Free hosted claim check

A Cloudflare Worker that lets visitors without an API key use "Check with AI" on the claim
checker, paid for by onrecord's own Anthropic key and capped per day.

What it accepts and adds:

- It takes only the conversation (`{ messages }`) and adds the instructions and tools from
  [`site/check-prompt.json`](../site/check-prompt.json), the model and `max_tokens` itself.
  A caller can't swap in their own prompt or model, so it can't be used as a general free
  chatbot.
- It answers only pages from `ALLOWED_ORIGINS`.

Caps, counted in model calls per UTC day (a check takes about 3–6):

- `PER_VISITOR_CALLS`: per visitor. Visitors are counted by a hash of their IP and the day;
  the IP itself is never stored.
- `DAILY_CALLS`: everyone combined.
- **Set a monthly spend limit on the Anthropic workspace as well.** That limit is the hard
  stop on cost, whatever happens to the counters.

Scope: "Ask the record" (the per-topic chat) still needs the reader's own key. It sends a
much larger context.

## Deploy (once)

You need a Cloudflare account (the free plan is enough) and an Anthropic API key, ideally in
a separate workspace with a spend limit.

```bash
cd worker
npx wrangler login
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler deploy
```

`deploy` prints the URL, e.g. `https://onrecord-ai.<you>.workers.dev`. Then, on GitHub, go to
repository Settings → Secrets and variables → Actions → Variables, and add
`ONRECORD_AI_ENDPOINT` with that URL. The next "Update data and site" run writes `ai.json`
and allows the endpoint in the site's Content-Security-Policy. To switch the free check off,
delete the variable.

Redeploy the worker (`npx wrangler deploy`) whenever `site/check-prompt.json` changes, so
the worker and the site send the same instructions.

## Try it locally

```bash
cd worker
printf 'ANTHROPIC_API_KEY=...\n' > .dev.vars
npx wrangler dev --port 8798
```

`.dev.vars` is gitignored. Point a local export at it by writing `build/ai.json` with
`{"endpoint":"http://127.0.0.1:8798"}` and adding that origin to `connect-src` in
`build/index.html`.
