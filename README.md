# onrecord

**What governments actually did, sourced line by line.**

onrecord follows government decisions from the paper trail they leave: the executive
orders, gazette notices, votes, regulations, and official statistics. It shows what was
*said*, what was *legally done*, and what the official numbers did afterwards, with
every item linked to the primary source.

Three topics so far:

- **US–Canada trade**: every US presidential action and Canadian government announcement
  on tariffs since January 2025, against *both* countries' official monthly trade figures.
- **EU–US trade**: US actions affecting the EU, the EU's own legal acts and proposals
  (countermeasures, their suspensions, the framework agreement), and both sides' figures.
- **Accountability**: every executive order since January 20, 2025, every pardon and
  commutation the Justice Department has published, and every donation the presidential
  inaugural committee reported to the FEC, plus a name lookup across all records.

> Status: early. The data pipeline works and runs daily. The site is a first view.
> Everything on the [roadmap](docs/roadmap.md) is open for contributors.

## Principles

1. **Primary sources only.** Every record points to the official document it came
   from, plus where in that document to look. No source, no record.
2. **Said ≠ done.** A news release announcing a tariff is a *claim*. The order that
   imposes it is an *event*. The trade data afterwards is an *observation*. These are
   stored and shown separately, always.
3. **Keep everything.** Raw documents are archived byte for byte with a SHA-256 hash.
   If a government edits a document after publishing it, both versions are kept.
4. **Show timing, don't assert cause.** Lining up a tariff date with a trade chart is
   useful, but it doesn't prove the tariff caused the change. We say so.
5. **Interpretation is a separate, labelled layer.** AI-written explanations (planned)
   may only cite verified records, and are always marked as interpretation.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run onrecord pull      # fetch every topic from its official sources (~3 min)
uv run onrecord export    # write the static site to build/
python -m http.server --directory build 8000
```

Other commands: `onrecord status`, `onrecord sources`, `onrecord reparse` (re-run parsers
over the archive with no network), `onrecord rebuild` (recreate the database from the
archive).

## Sources so far

| Adapter | Jurisdiction | What it gives us | Key needed |
|---|---|---|---|
| `federal_register` | US | Executive orders, proclamations, rules, notices: signing, publication, effective dates | no |
| `canada_news` | CA | Government of Canada news releases (claims) | no |
| `statcan_trade` | CA | Monthly merchandise trade by partner (Table 12-10-0011) | no |
| `fred_trade` | US | US Census Bureau goods trade by country, republished on FRED | no |
| `eurlex` | EU | EU regulations, decisions, Commission proposals (EUR-Lex SPARQL) | no |
| `eurostat_trade` | EU | EU27 monthly goods trade by partner (Eurostat) | no |
| `doj_clemency` | US | Pardons and commutations (DOJ Office of the Pardon Attorney) | no |
| `fec_form13` | US | Donations to the presidential inaugural committee (FEC Form 13) | optional `FEC_API_KEY` |

Wanted next: Canada Gazette (the legal instruments behind Canadian countermeasures),
USITC tariff schedule, court dockets, lobbying disclosures, federal contracts,
Congress.gov. See [docs/roadmap.md](docs/roadmap.md).

## How it works

```
government APIs ──fetch()──▶ raw archive (bytes + sha256, append-only manifest)
                                   │
                              parse()   pure, offline, tested against real fixtures
                                   ▼
                 SQLite: documents · events · claims · observations
                                   │
                              export()
                                   ▼
             static site + JSON + the whole database (free hosting)
```

Full design: [docs/architecture.md](docs/architecture.md). Hosting and costs:
[docs/hosting.md](docs/hosting.md). What we count as a fact:
[docs/methodology.md](docs/methodology.md).

## Ask the record (optional AI)

The site has an "Ask the record" panel. Paste your own Anthropic or OpenAI API key and
ask questions in plain language. The model sees only the archived records and must cite
them; citations link back to the timeline item and its primary source. Answers are
labelled as interpretation.

There is no onrecord server: the key stays in your browser (in memory, or in local
storage if you tick "remember") and requests go directly to the provider. A question
costs a few cents on your account (about 20k tokens of records per first question,
cached for follow-ups). Code: [`site/chat.js`](site/chat.js).

## Use the data

Every deployment publishes `data/timeline.json`, `data/series.json`, and the full
`data/onrecord.sqlite`, which you can query with SQL in your browser through
[Datasette Lite](https://lite.datasette.io/) (link in the site footer). The `data`
branch of this repo is the raw archive, and its git history records every document we
saw and when.

## Contributing

The best first contribution is a new source adapter: one file, one fixture, one test,
and no API keys needed to run the tests. Start with [CONTRIBUTING.md](CONTRIBUTING.md).
Coding agents are welcome; see [AGENTS.md](AGENTS.md).

## License

- **Code:** [GNU AGPL-3.0](LICENSE). You may use, modify, and host it, but if you run
  a modified version as a service you must publish your changes under the same license.
- **Data and written content we produce:** [CC BY-SA 4.0](LICENSE-DATA.md).
  The underlying government documents keep their original terms (US federal works are
  public domain; Canadian content is under the Open Government Licence – Canada and the
  Statistics Canada Open Licence).
- Contributions require agreeing to the [CLA](CLA.md).
