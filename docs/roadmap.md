# Roadmap

Each item is sized to be a separate issue. ⭐ = good first issue.

## Sources (adapters)

- ⭐ **Canada Gazette Part I/II**: the legal orders behind Canadian countermeasures
  (e.g. *United States Surtax Order*). RSS at `https://gazette.gc.ca/rss/p2-eng.xml`
  lists issues, so each issue's index page needs crawling. Highest priority: right
  now Canada's side has announcements but not the legal acts.
- ⭐ **US Census international trade API**: US-side monthly imports/exports by
  country and HS code. Needs a free key (`CENSUS_API_KEY`). Lets us compare US and
  Canadian figures for the same flows (they never match exactly, and that's worth showing).
- **USITC Harmonized Tariff Schedule**: what the tariff rate on a product actually
  is, by date. Needed for the "tariff status tracker".
- **CBP CSMS messages**: the operational guidance that says when duties actually start
  being collected.
- **Court dockets** (CourtListener API): challenges to tariff actions (e.g. IEEPA cases).
- **LEGISinfo / Congress.gov**: bills and votes.
- **EU**: EUR-Lex (legal acts), Eurostat Comext (trade), TARIC (tariffs), for an EU–US topic.
- **Lobbying**: US Senate LDA filings, Canada's Registry of Lobbyists.

## Features

- ⭐ **Relevance review**: flag off-topic documents in a topic (e.g. a Federal Register
  rule that only mentions Canada in passing), via a reviewed exclude list per topic.
- **Full-text archive** for Federal Register documents (`raw_text_url`).
- **Verified extraction** (see architecture.md): effective dates, rates, HTS codes,
  legal authority, with quoted passages.
- **Tariff status tracker**: announced → signed → in effect → suspended → struck down,
  per measure, on both sides.
- **Said-vs-did ledger**: link each claim to the events that did or didn't follow.
- **Document change alerts**: surface when a published document's bytes change.
- **Statistical revision view**: first estimate vs latest, per month.
- **Watchlists / RSS / email** per topic, measure, or HTS code.
- **API + MCP server** over the SQLite file.
- **Narratives**: labelled AI explanations that may cite only verified records.
- **Media comparison**: how coverage described an action vs what the instrument says.
- **Chat**: questions answered from the record, with citations; unanswerable
  questions become proposed topic expansions.
