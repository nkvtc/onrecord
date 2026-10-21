# Contributing

Thanks for helping. This project only works if the record is right, so the bar is
simple: **every change must keep every record traceable to an official source.**

## Setup

```bash
uv sync
uv run pytest          # offline; uses saved real responses in tests/fixtures/
uv run onrecord pull   # optional: live fetch, no keys needed for current sources
```

Before opening a PR: `uv run ruff format . && uv run ruff check . && uv run pytest`.

## Ways to help, easiest first

1. **Report a data error.** Use the "Data error" issue template. Include the item, what
   is wrong, and the official source that shows it. This is the most valuable issue.
2. **Tune a topic.** Topics in `topics/*.toml` decide what we collect. If we're missing
   documents or including noise, adjust the query and say why. No Python needed.
3. **Add a source adapter.** See below. Issues labelled `adapter` describe wanted sources.
4. **Add a topic.** E.g. EU–US trade. Usually needs one or two new adapters first.
5. **Improve the site.** `site/` is plain HTML/CSS/JS with no build step.

## Adding a source adapter

An adapter lives in `src/onrecord/adapters/<name>.py` and has two methods:

- `fetch(topic)` talks to the network and yields `RawDocument`s that are in scope.
- `parse(raw)` is a **pure function**: bytes in, `ParseResult` out. No network, no clock,
  no randomness. This is what makes the archive replayable.

Steps:

1. Copy the closest existing adapter (`federal_register.py` for a document API,
   `statcan_trade.py` for statistics).
2. Register it in `src/onrecord/adapters/__init__.py`.
3. Add a config table for it to the relevant topic TOML.
4. Run it live once, then copy 1–3 **real** raw responses from `data/raw/<name>/` into
   `tests/fixtures/<name>/`. Never hand-write fixtures. They must be what the server
   actually returned.
5. The contract tests in `tests/test_contract.py` now run against your adapter
   automatically. Add a few source-specific assertions in `tests/test_adapters.py`.

Rules for parsers:

- **Never invent a value.** If the source doesn't state an effective date, don't infer
  one. Leave it out and open an issue for a full-text extraction step instead.
- Statements go in `claims`, legal acts in `events`, numbers in `observations`.
  When unsure, it's a claim.
- Every event and claim needs a `locator` that tells a human exactly where to look.
- Bump the adapter's `version` when its output changes.
- Be polite to servers: use the shared `Http` client and keep the rate limit.

## Pull requests

- One adapter or one change per PR.
- Explain *why*, and link the official documentation for any source you add.
- If an AI agent wrote some or all of the PR, say so in the description. That's fine.
  You're still responsible for having read and run it.
- By opening a PR you agree to the [CLA](CLA.md).

## Neutrality

We do not editorialize in the data layer. Titles come from the source. Summaries come
from the source. If you think a government document is misleading, the fix is to add
the other primary source that shows it (a later amendment, the statistics, the court
ruling), not to reword the record.
