# Architecture

## Layers

```
1. Collect     adapters: fetch()  ── deterministic code, no AI
2. Archive     raw/<source>/<sha>.json + manifest.jsonl (append-only, on the `data` branch)
3. Parse       adapters: parse()  ── pure functions, tested on real fixtures
4. Index       SQLite: documents, events, claims, series, observations
5. Extract     (planned) LLM extraction from full text → candidate records
6. Verify      (planned) every candidate checked against its cited passage
7. Explain     (planned) narratives that may only cite verified records
8. Serve       static site, JSON, SQLite download; (planned) API + MCP server
```

Layers 1–4 and 8 exist today. The rule that holds the design together: **nothing in a
higher layer may state a fact that a lower layer can't point to.**

## Record types

| Type | Meaning | Example |
|---|---|---|
| `Event` | Something that legally happened | Proc. 11065 *signed* 2026-09-08 |
| `Claim` | Something an official body said | Finance Canada: "$155B tariff package" |
| `Observation` | A number from an official statistical release | Canada exports to US, Aug 2026: 54,346.5 CAD M |
| `RawDocument` | The bytes the server returned | sha256 `3fa1…` |

Every Event and Claim carries `locator` (where in the source) and `extracted_by`
(`rule:<adapter>@<version>` today, `llm:<model>` + verifier status later).

Observations keep `released_at`, so statistical revisions are stored next to the
original figure instead of overwriting it. "The first estimate said X, the revision
said Y" is part of the record.

## Why these choices

- **SQLite, not Postgres or a graph database.** It ships as one file inside the static
  site, can be queried in the browser, and handles millions of rows. The "knowledge
  graph" is a set of tables with foreign keys. Move to Postgres when there's a write-heavy
  service that needs it, not before.
- **fetch/parse split.** Parser bugs get fixed by `onrecord reparse` without touching
  government servers, and every parser is testable offline.
- **Git as the audit log.** The `data` branch history is a public, timestamped,
  tamper-evident record of what each source served and when.
- **No AI in ingestion.** LLMs are good at extraction and bad at being a source of truth.
  They come in at layer 5, behind a verifier, with their output labelled.

## Planned: extraction and verification (layers 5–6)

1. Archive full text for each document (e.g. Federal Register `raw_text_url`).
2. An extraction agent reads the text and proposes records: effective dates, tariff
   rates, HTS codes, affected countries, legal authorities cited. Each proposal must
   quote the exact passage, with character offsets.
3. A verifier checks that the quote exists verbatim at those offsets and that it
   supports the proposed value. Mismatches are rejected, not repaired.
4. Accepted records are stored with `extracted_by="llm:<model>"` and `verified_by`.
   The UI marks them as machine-extracted.

## Planned: query-driven growth

When a user asks something the graph can't answer ("what happened to Canadian dairy
tariffs?"), the system logs the gap, proposes a topic or query change, and (after
review) adds it to `topics/`. The graph grows from real questions, through the same
verified pipeline. It never grows from an agent writing facts directly.
