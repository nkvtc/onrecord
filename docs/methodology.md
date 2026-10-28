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
- The `eurlex` filter keeps acts whose English title mentions the United States and drops
  acts authored only by the Commission's health directorate (animal and plant health
  import rules). Some anti-dumping notices on US products are kept; they are trade
  measures, though not part of the tariff dispute.
- US figures come from the Census Bureau via FRED and are not seasonally adjusted;
  Canadian and EU figures shown are seasonally adjusted. The chart says which.

## Accountability records

The accountability topic holds executive orders, clemency grants and reported donations.
It is the part of the project most likely to be misread, so its rules are stricter:

- **No labels.** We don't call anything corrupt, suspicious or improper. We show what
  official records say: who signed what, who was granted clemency, who reported giving
  how much to whom.
- **No automatic links between people.** A donor and a pardon recipient with the same
  name may be different people. The site's name lookup searches every record but always
  says that a matching name is not proof of a connection. A connection is shown as a
  fact only when a primary source states it, added by hand through a reviewed pull
  request with that source cited.
- **As filed.** Donor names, amounts, dates and places are reproduced exactly as the
  filer reported them, typos included (e.g. a city paired with the wrong state). We
  don't correct filings; we link to them. Street addresses are not republished.
- **Amendments supersede.** Committees amend reports. Only the latest amendment of each
  report is counted, so donations aren't double counted; earlier filings stay archived.
- **Where the source is ambiguous, so are we.** When the Justice Department lists
  pardons and commutations together in one table without saying which applies to whom,
  each entry is labelled "pardon or commutation", not guessed.
- **Known gaps.** Mass grants by proclamation (e.g. January 6 defendants) are recorded as
  one item: the Justice Department page doesn't list the individuals. Donations to other
  committees (super PACs, campaign committees) and lobbying disclosures aren't collected yet.

## Corrections

Errors are reported as GitHub issues using the "Data error" template. Fixes go through
pull requests, so every correction is public with its reason. Archived source documents
are never edited. A correction changes a parser or topic, and the record is rebuilt.
