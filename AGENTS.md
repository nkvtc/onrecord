# Instructions for coding agents

This file is for AI coding agents (Claude Code, Codex, Cursor, etc.) working in this
repository. Humans should read CONTRIBUTING.md, which has the same rules in more detail.

## What this project is

A pipeline that archives official government documents and statistics, parses them
into four record types, and publishes a static site. Accuracy and traceability matter
more than features. A wrong record is worse than a missing one.

## Commands

```bash
uv sync
uv run pytest                      # must pass; offline
uv run ruff format . && uv run ruff check .
uv run onrecord pull --source <adapter>   # live fetch (network)
uv run onrecord export && python -m http.server --directory build 8000
```

## Layout

- `src/onrecord/models.py`: RawDocument, Event, Claim, Observation. Read this first.
- `src/onrecord/adapters/`: one module per source. `base.py` defines the contract.
- `src/onrecord/store.py`: raw archive + SQLite. `manifest.jsonl` is append-only.
- `src/onrecord/export.py`: JSON + SQLite for the site.
- `topics/*.toml`: what to collect, per adapter.
- `site/`: static frontend, no build step, no dependencies.
- `tests/fixtures/<adapter>/`: real saved server responses.

## Hard rules

1. `parse()` must be pure: no network, no current time, no randomness.
2. Never fabricate fixture data. Fixtures are copied from `data/raw/` after a real
   fetch. If you can't reach the source, stop and say so instead of inventing a response.
3. Never infer facts a source doesn't state (dates, rates, actors). Leave the field out.
4. Claims (what was said) and events (what legally happened) are never merged.
5. Every Event and Claim has a non-empty `locator`.
6. Don't edit files under `data/raw/` or rewrite `manifest.jsonl`.
7. Don't add runtime dependencies without a clear reason in the PR description.
8. Don't add LLM calls to the ingestion path. LLM extraction will be a separate,
   verified layer (see docs/architecture.md).

## Good tasks for agents

Issues labelled `adapter` or `good first issue` are scoped so that one agent session can
finish them: one new module, real fixtures, tests. Link the source's official API docs
in the PR and state which model or agent produced the change.
