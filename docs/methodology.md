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

## Historical comparisons

Comparisons across presidents are where a careless count does the most damage, so each
one is computed in `src/onrecord/panels.py` with a written rule, and the site prints
that rule under the chart.

- **Executive orders** count distinct order numbers by signing date. The Federal
  Register API also returns corrections and republished copies under the same number;
  counting documents instead of numbers overstates totals (Obama: 294 documents, 276
  orders). The comparison uses days in office, so a president part-way through a term is
  compared with others at the same day, not with their full totals. Clinton is left out
  because the online record starts in 1994.
- **Clemency** uses the Justice Department's own per-president tables of petitions
  granted. Grants by proclamation to whole groups are not in those tables, and the page
  says so. A current term appears only when DOJ publishes it; until then the page shows
  the count from DOJ's grant list, labelled as a different measure.
- **Inaugural money** is the total each committee reported to the FEC in its latest
  supplement or 90-day report, in nominal dollars (not adjusted for inflation).

## Spending and revenue

- **Tariff revenue** is customs duties from the Monthly Treasury Statement, Table 9, as
  *net* receipts: collections minus refunds in the month. A negative month means refunds
  exceeded collections. The Treasury figure shows that refunds happened, not why; the
  reason has to come from another primary source (a court order, a CBP notice), and the
  page says so instead of guessing.
- **The spending map** shows obligations on federal awards reported to USAspending, by
  place of performance, per person. It includes Social Security, Medicare and other
  direct payments, contracts, grants and loans; it excludes federal salaries.
  Per-person figures are driven by things that aren't favoritism: retirees, military
  bases, and where contractors and claims processors are located. A state's color can
  reflect where a Medicare contractor sits rather than where people get care. The page
  shows each state's awarding agencies for that reason.
- **Top contractors** are listed as reported, by recipient ID. One company can appear
  more than once (parent and subsidiary registrations); we don't merge them, because
  merging by name is how wrong totals happen.
- **GAO reports** are the auditor's own published findings, stored as claims. The feed
  only carries recent items, so the archive starts on the day collection began.
- **Not yet**: Inspector General reports (oversight.gov blocked automated requests).

## The federal budget

- **What the money was spent on** is net outlays by budget function from the Monthly
  Treasury Statement, Table 9, for each fiscal year (October to September). "Net" means
  money paid out minus money that came back in for the same purpose, so a function can
  be negative (deposit insurance premiums, loan repayments). "Out of every dollar"
  shares are taken over the positive lines only, so they add up to 100%. The year in
  progress is labelled with how many months it covers.
- **Where the money comes from, and where it goes** (the flow and pie views) uses the
  same table. In: every receipt line, plus borrowing (net outlays minus receipts), plus
  money that came back in for a purpose, which the budget subtracts from spending. Out:
  every function with positive net outlays. Both sides then total the same gross amount.
  Federal money is pooled, so the chart does not claim which tax paid for which program.
- **Collected vs spent** uses the same table's total receipts and total net outlays.
  The deficit is the difference. Nominal dollars, not adjusted for inflation or GDP.
- **Departments** are net outlays by agency from Table 5. Bureau lines are listed as the
  Treasury prints them; they are gross of transfers inside the government, so a bureau
  can exceed its department's net total. Each agency's mission is its own text from
  USAspending, quoted, never paraphrased. "What its money funds" is the agency's gross
  outlays by budget function as reported to USAspending, a different measure from
  Treasury's net figure, and the page labels it so.
- **Improper payments** are the agencies' own estimates, from statistical samples,
  reported to OMB under the Payment Integrity Information Act and published at
  paymentaccuracy.gov. "Improper" includes payments that were the right amount but
  lacked required documentation, so it is not a fraud estimate; "unknown" means the
  agency could not determine whether a payment was proper. Each program's confidence
  interval and margin of error are shown where the agency reported them. The programs
  measured change from year to year, so totals across years are not strictly
  comparable.

## Bills in Congress

- **Which bills.** Bills and joint resolutions (the kinds that can become law) with at
  least one recorded vote on the bill itself: passage, passage under suspension of the
  rules, agreeing to the other chamber's version, a conference report, or a veto
  override. Procedural votes (rules, motions to recommit) are not counted. Bills are
  found through House roll calls, because senate.gov refuses automated requests; a bill
  only the Senate has voted on appears once the House votes on it.
- **Contested** means that on at least one of those votes the losing side had at least
  40% of the yea and nay votes, or most House Republicans and most House Democrats voted
  on opposite sides. It is a rule about the vote record, not a judgment about the bill.
- **What it would change** is the Congressional Research Service's summary of the
  latest version it has summarized, quoted as Congress.gov publishes it, with the version
  and date. CRS is Congress's nonpartisan research agency. Some bills have no summary yet.
- **Vote counts.** House counts and the party breakdown come from the Clerk's roll call
  file. Senate counts are as stated in the bill's official actions ("51 - 50. Record Vote
  Number: 372"). "Present" and not voting are left out of the margin.
- **How each representative voted** uses the full Clerk roll call for every House vote
  that decided a bill (other roll calls are archived as their header only). "With their
  party" means the member voted the same way as most members of their party who voted
  yea or nay. Senate member votes are not shown: senate.gov does not allow automated
  access, and onrecord does not work around that.
- **Spending bills** are those whose title mentions appropriations, rescissions,
  reconciliation or the debt limit, or that Congress.gov files under Economics and Public
  Finance. "Republicans cast 80% of the yes votes" adds up the yes votes by party on the
  last House vote on each bill. A yes vote is a vote for the bill as it stood, not for
  every provision in it. CBO cost estimates are linked where Congress.gov lists them.

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

## Past presidents' clemency

Named pardons and commutations by Presidents Clinton, G. W. Bush, Obama, Trump (first
term) and Biden come from the Pardon Attorney's per-term pages, archived and parsed like
the current term. Our counts match the Justice Department's own statistics for every
term except two small differences we haven't resolved: Obama's pardons (208 parsed vs.
212 counted by DOJ) and Clinton's commutations (65 vs. 61). Where one table row names
several people (Biden's January 19, 2025 family pardons), each person is an item. Where
a row describes a group instead ("the staff of the Select Committee"), the group is one
item and nobody is named. Mass commutations listed as one line ("Commutation granted to
1,499 individuals") are one item linking to the recipient list.

## Checking a claim

"Check a claim" searches every record across topics. The ranking is plain word matching
weighted by how rare each word is, with a bonus for phrases, for records of the type the
question names (pardon, executive order, bill), and, when the question names a president,
a filter to records that president signed. It is a search, not a verdict: the page shows
what matched and lets the reader decide.

The optional AI step uses the reader's own key. It is told what the archive covers, to
cite only records it found, to be exact about who and what (a pardon for a committee's
staff is not a pardon for the president's staff), and that a missing record means the
archive doesn't settle a claim, not that it didn't happen. Its answer is labelled as an
AI reading. Shared links carry record keys and sides only, never text, and say who chose
the sides.

## Corrections

Errors are reported as GitHub issues using the "Data error" template. Fixes go through
pull requests, so every correction is public with its reason. Archived source documents
are never edited. A correction changes a parser or topic, and the record is rebuilt.
