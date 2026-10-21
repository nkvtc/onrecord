# Methodology

How onrecord decides what counts as a fact, and where its limits are. Changes to this
document are made in public, with a reason, in a pull request.

## What we record

- **Events** come only from legal instruments and official registers: the Federal
  Register, the Canada Gazette, legislative journals, court dockets. A date is recorded
  only if the source states it.
- **Claims** are statements by government bodies (news releases, speeches, briefings),
  dated when they were made. A claim records that something was *said*, not that it is true.
- **Observations** come only from national statistical agencies and official data
  services, with the release date and the basis (e.g. customs vs balance of payments,
  seasonally adjusted or not) in the series label.

## What we do not do

- We don't use news articles as sources for the record. Media comparison, when built,
  will be a separate labelled layer that compares coverage *to* the record.
- We don't infer missing values. Example: the Federal Register API has no effective
  date for Executive Order 14193 even though the order's text sets one. We leave it
  empty until a verified full-text extraction step can cite the sentence.
- We don't claim causation. Putting a tariff date on a trade chart shows timing.
  Trade figures also move with exchange rates, prices, inventories, seasons, and
  importers rushing ahead of a tariff (visible in early 2025).

## Selection is a choice

What we collect is set by the topic files in `topics/`. Keyword and query choices
decide what appears, so they're public, versioned, and open to challenge. Known
current limits:

- The `canada_news` keyword filter can miss releases that don't use any of the
  keywords, and can include tangential ones.
- The Federal Register "Canada tariff" query includes some unrelated documents (it is
  full-text search). A relevance review step is on the roadmap.
- Canadian legal instruments (Canada Gazette orders) aren't collected yet, so Canada's
  side currently shows announcements only, not the orders that implemented them.

## Corrections

Errors are reported as GitHub issues using the "Data error" template. Fixes go through
pull requests, so every correction is public with its reason. Archived source documents
are never edited. A correction changes a parser or topic, and the record is rebuilt.
