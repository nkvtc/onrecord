"""Comparison panels: computed views over archived records, each with its counting rule.

A panel is only as fair as the way it counts, so every panel carries a plain-language
`rule` the site prints next to the chart. Change a rule here and the page changes with
it; nothing is hand-entered.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date

from .adapters.congress_bills import URL_TYPE, decides_bill
from .store import Store

# Presidential terms covered by the Federal Register's online records (1994 onward).
# Clinton is left out: his first year predates the online record, so his count would be low.
TERMS = [
    ("George W. Bush", "george-w-bush", "2001-01-20", "2009-01-20"),
    ("Barack Obama", "barack-obama", "2009-01-20", "2017-01-20"),
    ("Donald Trump, 1st term", "donald-trump", "2017-01-20", "2021-01-20"),
    ("Joe Biden", "joe-biden", "2021-01-20", "2025-01-20"),
    ("Donald Trump, 2nd term", "donald-trump", "2025-01-20", None),
]


def _latest_docs(store: Store, source: str):
    return store.db.execute(
        """SELECT * FROM documents d WHERE source = ? AND version = (
               SELECT MAX(version) FROM documents
               WHERE source = d.source AND source_id = d.source_id)""",
        (source,),
    ).fetchall()


def eo_pace(store: Store, today: date) -> dict:
    orders: dict[str, dict] = {}
    for doc in _latest_docs(store, "federal_register"):
        if doc["doc_type"] != "executive_order":
            continue
        x = json.loads(doc["extra_json"] or "{}")
        num, signed = x.get("executive_order_number"), x.get("signing_date")
        if num and signed:
            # Keyed by number: corrections and reprints share their order's number.
            orders.setdefault(num, {"president": x.get("president"), "signed": signed})

    terms = []
    for label, president, start, end in TERMS:
        stop = end or today.isoformat()
        dates = sorted(
            o["signed"]
            for o in orders.values()
            if o["president"] == president and start <= o["signed"] < stop
        )
        s = date.fromisoformat(start)
        days = [(date.fromisoformat(d) - s).days for d in dates]
        points, n = [], 0
        for day in days:
            n += 1
            if points and points[-1][0] == day:
                points[-1][1] = n
            else:
                points.append([day, n])
        terms.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "current": end is None,
                "total": len(days),
                "days_in_office": ((date.fromisoformat(end) if end else today) - s).days,
                "points": points,
            }
        )
    current = next((t for t in terms if t["current"]), None)
    day_now = current["days_in_office"] if current else None
    # The comparison that matters: each president's count at the same day in office.
    for t in terms:
        t["by_same_day"] = (
            max((n for d, n in t["points"] if d <= day_now), default=0)
            if day_now is not None
            else None
        )
    return {
        "day_now": day_now,
        "terms": terms,
        "source": "Federal Register API",
        "rule": (
            "Counts distinct executive order numbers, by signing date, from the Federal "
            "Register. Corrections and republished copies share their order's number, so "
            "they are not counted twice. Clinton is left out because the online record "
            "starts in 1994, a year into his term."
        ),
    }


def clemency_by_president(store: Store, today: date) -> dict:
    stats = next(iter(_latest_docs(store, "doj_clemency_stats")), None)
    presidents = json.loads(stats["extra_json"])["presidents"] if stats else []
    # The current term isn't in DOJ's statistics table until the term is over, so
    # report what DOJ's grant list shows, clearly labelled as a different count.
    current = None
    # Past terms' grant pages are archived too (topics/history.toml); only the open-ended
    # current-term page counts here.
    lists = [d for d in _latest_docs(store, "doj_clemency") if "present" in d["canonical_url"]]
    if lists:
        rows = store.db.execute(
            f"""SELECT subject FROM events WHERE document_id IN
                ({",".join("?" * len(lists))})""",
            [d["id"] for d in lists],
        ).fetchall()
        current = {
            "named_grants": sum(1 for r in rows if r["subject"]),
            "grants_by_proclamation": sum(1 for r in rows if not r["subject"]),
            "url": lists[0]["canonical_url"],
        }
    return {
        "presidents": presidents,
        "current_term": current,
        "url": stats["canonical_url"] if stats else None,
        "source": "DOJ Office of the Pardon Attorney, clemency statistics",
        "rule": (
            "Pardons and commutations granted on petitions, as tabulated by the Justice "
            "Department per president and fiscal year. Grants by proclamation to whole "
            "groups (e.g. Carter's draft-evader pardon, Biden's marijuana pardons, "
            "January 6 pardons) are not in these tables. Remissions and respites are left out."
        ),
    }


def inaugural_totals(store: Store, today: date) -> dict:
    rows = []
    for doc in _latest_docs(store, "fec_inaugural_totals"):
        x = json.loads(doc["extra_json"] or "{}")
        if "total_receipts" not in x:
            continue
        rows.append(
            {
                "label": x["label"],
                "inauguration": x["inauguration"],
                "committee": x.get("committee_name"),
                "total": x["total_receipts"],
                "citation": doc["citation"],
                "report": x.get("report"),
                "url": doc["canonical_url"],
            }
        )
    rows.sort(key=lambda r: r["inauguration"])
    return {
        "rows": rows,
        "source": "FEC Form 13 filings",
        "rule": (
            "Total donations each inaugural committee reported to the FEC, from its most "
            "recent post-inaugural supplement (or 90-day report if it filed no supplement). "
            "Not adjusted for inflation. Inaugural committees have no donation limits."
        ),
    }


BUILDERS: dict[str, Callable[[Store, date], dict]] = {
    "eo_pace": eo_pace,
    "clemency_by_president": clemency_by_president,
    "inaugural_totals": inaugural_totals,
}


def build_panels(store: Store, panels: list[dict], today: date) -> list[dict]:
    out = []
    for p in panels:
        # Extra keys in the topic file (series, since, ...) are passed to the builder.
        options = {k: v for k, v in p.items() if k not in ("kind", "title")}
        out.append({**p, **BUILDERS[p["kind"]](store, today, **options)})
    return out


# ---- Follow the money -----------------------------------------------------------


def _rows(store: Store, kind: str) -> list[dict]:
    """Extras of the latest usaspending documents of one kind."""
    out = []
    for doc in _latest_docs(store, "usaspending"):
        x = json.loads(doc["extra_json"] or "{}")
        if x.get("kind") == kind:
            out.append(x)
    return out


def monthly_revenue(store: Store, today: date, series: str, since: str = "2015-01-01") -> dict:
    rows = store.db.execute(
        """SELECT period, value FROM observations o WHERE series_id = ? AND released_at = (
               SELECT MAX(released_at) FROM observations
               WHERE series_id = o.series_id AND period = o.period)
           ORDER BY period""",
        (series,),
    ).fetchall()
    points = [[r["period"], r["value"]] for r in rows if r["period"] >= since]
    years: dict[str, dict] = {}
    for period, value in points:
        y = years.setdefault(period[:4], {"year": period[:4], "total": 0.0, "months": 0})
        y["total"] += value
        y["months"] += 1
    meta = store.db.execute(
        "SELECT label, unit FROM series WHERE series_id=?", (series,)
    ).fetchone()
    return {
        "series": series,
        "label": meta["label"] if meta else series,
        "unit": meta["unit"] if meta else "",
        "points": points,
        "years": [{**y, "total": round(y["total"], 1)} for y in years.values()],
        "negative_months": [[p, v] for p, v in points if v < 0],
        "source": "US Treasury, Monthly Treasury Statement, Table 9",
        "rule": (
            "Customs duties as net receipts: what was collected in the month minus refunds "
            "paid out. A bar below zero means refunds exceeded collections that month. "
            "Calendar-year totals add up the months shown; a partial year says how many "
            "months it covers. Nominal dollars."
        ),
    }


def spending_map(store: Store, today: date) -> dict:
    states = {str(x["fiscal_year"]): x["rows"] for x in _rows(store, "geo_state")}
    counties = {str(x["fiscal_year"]): x["rows"] for x in _rows(store, "geo_county")}
    agencies = {}
    for x in _rows(store, "agencies_by_state"):
        agencies.setdefault(str(x["fiscal_year"]), {})[x["state"]] = x["rows"]
    return {
        "states": dict(sorted(states.items())),
        "counties": counties,
        "agencies": agencies,
        "source": "USAspending.gov",
        "rule": (
            "Obligations on federal awards (contracts, grants, loans and direct payments, "
            "including Social Security and Medicare) by place of performance, per fiscal "
            "year (October to September), divided by population. Federal salaries are not "
            "included. Place of performance can be where a contractor or claims processor "
            "operates rather than where people use the benefit, so check the agency "
            "breakdown before reading a state's color as favoritism."
        ),
    }


def top_contractors(store: Store, today: date) -> dict:
    found = sorted(_rows(store, "top_contractors"), key=lambda x: x["fiscal_year"])
    latest = found[-1] if found else {"fiscal_year": None, "rows": []}
    return {
        "fiscal_year": latest["fiscal_year"],
        "rows": latest["rows"],
        "source": "USAspending.gov",
        "rule": (
            "Contract obligations (award types A–D) in the fiscal year, by recipient as "
            "reported. The same company can appear more than once under different "
            "recipient IDs (parent and subsidiary registrations); we show them as reported "
            "rather than merge them."
        ),
    }


BUILDERS.update(
    {
        "monthly_revenue": monthly_revenue,
        "spending_map": spending_map,
        "top_contractors": top_contractors,
    }
)


# ---- Where the money goes -------------------------------------------------------


def _extras(store: Store, source: str, kind: str) -> list[dict]:
    out = []
    for doc in _latest_docs(store, source):
        x = json.loads(doc["extra_json"] or "{}")
        if x.get("kind") == kind:
            out.append(x)
    return sorted(out, key=lambda x: x.get("fiscal_year") or 0)


def _span(x: dict) -> dict:
    return {"fy": x["fiscal_year"], "through": x["through"], "months": x["months"]}


FISCAL_YEAR = "Fiscal years run October to September (FY2026 ended September 30, 2026)."


def budget_functions(store: Store, today: date) -> dict:
    years = []
    for x in _extras(store, "treasury_budget", "mts9"):
        lines = [r for r in x["rows"] if r["section"] == "outlays"]
        years.append(
            {
                **_span(x),
                "total": x["totals"].get("outlays"),
                "lines": sorted(lines, key=lambda r: -r["amount"]),
            }
        )
    return {
        "years": years,
        "source": "US Treasury, Monthly Treasury Statement, Table 9",
        "rule": (
            "Net outlays by budget function: what was paid out for each purpose, minus "
            "money that came back in for that purpose (premiums, loan repayments, asset "
            'sales), so a line can be negative. "Undistributed offsetting receipts" are '
            "payments between government accounts (such as agencies' contributions to "
            "employee pensions) taken off the total once. " + FISCAL_YEAR + " The year in "
            "progress shows its months so far. Nominal dollars, not adjusted for inflation."
        ),
    }


def receipts_outlays(store: Store, today: date) -> dict:
    years = []
    for x in _extras(store, "treasury_budget", "mts9"):
        receipts, outlays = x["totals"].get("receipts"), x["totals"].get("outlays")
        lines = [r for r in x["rows"] if r["section"] == "receipts"]
        years.append(
            {
                **_span(x),
                "receipts": receipts,
                "outlays": outlays,
                "deficit": outlays - receipts if receipts is not None and outlays else None,
                "receipt_lines": sorted(lines, key=lambda r: -r["amount"]),
            }
        )
    return {
        "years": years,
        "source": "US Treasury, Monthly Treasury Statement, Table 9",
        "rule": (
            "Total receipts and total net outlays in each fiscal year, as booked in the "
            "Monthly Treasury Statement; the gap between them is the deficit the Treasury "
            "borrowed to cover. Social Security's off-budget accounts are included. "
            + FISCAL_YEAR
            + " Nominal dollars."
        ),
    }


def money_flow(store: Store, today: date) -> dict:
    years = []
    for x in _extras(store, "treasury_budget", "mts9"):
        receipts, outlays = x["totals"].get("receipts"), x["totals"].get("outlays")
        if receipts is None or not outlays:
            continue
        rows = x["rows"]
        sources = sorted(
            (
                {"name": r["name"], "amount": r["amount"]}
                for r in rows
                if r["section"] == "receipts"
            ),
            key=lambda r: -r["amount"],
        )
        lines = [r for r in x["rows"] if r["section"] == "outlays"]
        uses = sorted(
            ({"name": r["name"], "amount": r["amount"]} for r in lines if r["amount"] > 0),
            key=lambda r: -r["amount"],
        )
        # Both sides balance on gross spending: net outlays are spending minus money that
        # came back in, so that money is shown as a source rather than netted away.
        came_back = -sum(r["amount"] for r in lines if r["amount"] < 0)
        years.append(
            {
                **_span(x),
                "receipts": receipts,
                "outlays": outlays,
                "borrowed": max(0.0, outlays - receipts),
                "surplus": max(0.0, receipts - outlays),
                "came_back": came_back,
                "sources": sources,
                "uses": uses,
            }
        )
    return {
        "years": years,
        "source": "US Treasury, Monthly Treasury Statement, Table 9",
        "rule": (
            "Left: every receipt line Treasury booked, plus what it borrowed to cover the gap "
            "(net outlays minus receipts), plus money that came back in for a purpose "
            "(premiums, loan repayments, payments between government accounts), which the "
            "budget nets out of spending. Right: every purpose with positive net outlays. "
            "Money is pooled in the Treasury, so the chart shows the totals on each side, "
            "not which tax paid for which program; only payroll taxes are earmarked by law, "
            "for Social Security and Medicare trust funds. " + FISCAL_YEAR + " Nominal dollars."
        ),
    }


# Monthly Treasury Statement agency names that USAspending spells differently.
AGENCY_ALIASES = {
    "Department of Defense--Military Programs": "Department of Defense",
    "Corps of Engineers": "Corps of Engineers - Civil Works",
}


def agency_outlays(store: Store, today: date) -> dict:
    profiles = {}
    for x in _extras(store, "usaspending_agencies", "agency"):
        profiles[x["name"]] = {
            "code": x["code"],
            "name": x["name"],
            "abbreviation": x.get("abbreviation"),
            "mission": x.get("mission"),
            "website": x.get("website"),
            "cj_url": x.get("cj_url"),
            "fiscal_year": x["fiscal_year"],
            "functions": sorted(x["rows"], key=lambda r: -(r["gross_outlays"] or 0)),
            "url": "https://www.usaspending.gov/agency/"
            + re.sub(r"[^a-z0-9]+", "-", x["name"].lower()).strip("-"),
        }
    years = []
    for x in _extras(store, "treasury_budget", "mts5"):
        agencies = []
        for a in x["rows"]:
            match = profiles.get(AGENCY_ALIASES.get(a["name"], a["name"]))
            agencies.append({**a, "profile": match["name"] if match else None})
        years.append(
            {
                **_span(x),
                "total": x["totals"].get("outlays"),
                "agencies": sorted(agencies, key=lambda a: -a["amount"]),
            }
        )
    return {
        "years": years,
        "profiles": profiles,
        "source": "US Treasury, Monthly Treasury Statement, Table 5; USAspending.gov",
        "rule": (
            "Net outlays by agency as the Treasury books them (Table 5). Bureau lines are "
            "the larger units the Treasury lists inside each agency, and they are gross of "
            "transfers between government accounts, so a bureau can show more than its "
            "department's net total (Medicare's trust funds inside HHS, for example). "
            'Missions are each agency\'s own description. The "what it funds" breakdown '
            "is the agency's gross outlays by budget function as reported to USAspending, "
            "which runs higher than Treasury's net figure. " + FISCAL_YEAR
        ),
    }


def improper_payments(store: Store, today: date) -> dict:
    docs = _extras(store, "payment_accuracy", "programs")
    if not docs:
        return {"years": [], "programs": [], "source": "PaymentAccuracy.gov", "rule": ""}
    latest = max(docs, key=lambda x: x["dataset_year"])
    rows = latest["rows"]
    years: dict[int, dict] = {}
    for r in rows:
        y = years.setdefault(
            r["fiscal_year"], {"fy": r["fiscal_year"], "amount": 0.0, "outlays": 0.0, "programs": 0}
        )
        if r.get("improper_and_unknown") is None:
            continue
        y["amount"] += r["improper_and_unknown"]
        y["outlays"] += r.get("outlays") or 0
        y["programs"] += 1
    last_fy = max(years)
    current = [r for r in rows if r["fiscal_year"] == last_fy and r.get("improper_and_unknown")]
    current.sort(key=lambda r: -r["improper_and_unknown"])
    by_agency: dict[str, float] = {}
    for r in current:
        by_agency[r["agency"]] = by_agency.get(r["agency"], 0) + r["improper_and_unknown"]
    return {
        "dataset_year": latest["dataset_year"],
        "fiscal_year": last_fy,
        "years": [
            {**y, "amount": round(y["amount"], 1), "outlays": round(y["outlays"], 1)}
            for _, y in sorted(years.items())
        ],
        "programs": current[:25],
        "program_count": len(current),
        "by_agency": sorted(
            ({"agency": k, "amount": round(v, 1)} for k, v in by_agency.items()),
            key=lambda a: -a["amount"],
        ),
        "url": "https://paymentaccuracy.gov/resources",
        "source": "Office of Management and Budget, PaymentAccuracy.gov",
        "rule": (
            "Each agency's own estimate, from statistical samples, of payments in programs "
            'it found susceptible to error. "Improper" means paid to the wrong party, in '
            "the wrong amount, or without the documentation the rules require, so it is not "
            'a fraud estimate and much of it is paperwork. "Unknown" means the agency '
            "couldn't tell whether the payment was proper. OMB publishes USD millions; shown "
            "here in billions. The set of programs measured changes from year to year, so totals "
            "across years are not strictly comparable."
        ),
    }


BUILDERS.update(
    {
        "budget_functions": budget_functions,
        "receipts_outlays": receipts_outlays,
        "money_flow": money_flow,
        "agency_outlays": agency_outlays,
        "improper_payments": improper_payments,
    }
)


# ---- Bills that split Congress ----------------------------------------------------

CLOSE = 0.2  # a margin of 20 points or less: the losing side had at least 40%
SUMMARY_CHARS = 1500


def _margin(yea: int, nay: int) -> float:
    return abs(yea - nay) / (yea + nay)


def _party_line(parties: list[dict]) -> bool:
    """Most Republicans and most Democrats voted on opposite sides."""
    by = {p["party"]: p for p in parties}
    r, d = by.get("Republican"), by.get("Democratic")
    if not r or not d or r["yea"] + r["nay"] < 10 or d["yea"] + d["nay"] < 10:
        return False
    return (r["yea"] > r["nay"]) != (d["yea"] > d["nay"])


def _status(bill: dict) -> str:
    if bill["law"]:
        return "Became law"
    if bill["vetoed"]:
        return "Vetoed"
    passed = {f["chamber"] for f in bill["rows"] if f["passed"]}
    if passed == {"House", "Senate"}:
        return "Passed both chambers"
    last = bill["rows"][-1] if bill["rows"] else None
    if last and not last["passed"]:
        return f"Failed in the {last['chamber']}"
    if passed:
        return f"Passed the {passed.pop()}"
    return "Voted on, not passed"


CODE = {"Yea": "Y", "Nay": "N", "Present": "P", "Not Voting": "-"}


def contested_bills(store: Store, today: date) -> dict:
    members: dict[str, dict] = {}
    house: dict[str, list[dict]] = {}
    for v in _extras(store, "congress_bills", "house_vote"):
        if v.get("bill") and v.get("yea") is not None and decides_bill(v.get("question", "")):
            house.setdefault(v["bill"], []).append(v)
            for m in v.get("members") or []:
                # The latest vote wins, so a member's party and name are their most recent.
                if m["id"] not in members or v["date"] >= members[m["id"]]["_date"]:
                    members[m["id"]] = {**m, "_date": v["date"]}
    order = sorted(members, key=lambda i: (members[i]["state"], members[i]["name"]))
    index = {mid: n for n, mid in enumerate(order)}

    def codes(v: dict) -> str | None:
        # One character per member in `order`: Y, N, P, - (not voting), or a space when
        # the member was not in the House for that vote.
        if not v.get("members"):
            return None
        out = [" "] * len(order)
        for m in v["members"]:
            out[index[m["id"]]] = CODE.get(m["vote"], "-")
        return "".join(out)

    bills = []
    for b in _extras(store, "congress_bills", "bill"):
        votes = [
            {
                "chamber": "House",
                "date": v["date"],
                "question": v["question"],
                "result": v["result"],
                "yea": v["yea"],
                "nay": v["nay"],
                "roll": v["roll"],
                "url": f"https://clerk.house.gov/Votes/{v['date'][:4]}{v['roll']}",
                "parties": [p for p in v["rows"] if p["yea"] + p["nay"] > 0],
                "party_line": _party_line(v["rows"]),
                "majority": v.get("majority"),
                "codes": codes(v),
            }
            for v in sorted(house.get(f"{b['type']}{b['number']}", []), key=lambda v: v["date"])
        ]
        votes += [
            {
                "chamber": "Senate",
                "date": f["date"],
                "question": f["text"].split(": ", 1)[-1],
                "result": "Passed" if f["passed"] else "Failed",
                "yea": f["yea"],
                "nay": f["nay"],
                "roll": f["roll"],
            }
            for f in b["rows"]
            if f["chamber"] == "Senate" and f["yea"] is not None and f["yea"] + f["nay"] > 0
        ]
        if not votes:
            continue
        votes.sort(key=lambda v: v["date"])
        closest = min(_margin(v["yea"], v["nay"]) for v in votes)
        party_line = any(v.get("party_line") for v in votes)
        summary = b["summary"]
        status = _status(b)
        bills.append(
            {
                "label": b["label"],
                "title": b["short_title"] or b["title"],
                "official_title": b["title"],
                "sponsor": b["sponsor"],
                "sponsor_party": b["sponsor_party"],
                "policy_area": b["policy_area"],
                "cbo": b.get("cbo") or [],
                "introduced": b["introduced"],
                "latest_action": b["latest_action"],
                "law": b["law"],
                "status": status,
                "active": status.startswith("Passed"),
                "url": (
                    f"https://www.congress.gov/bill/{b['congress']}th-congress/"
                    f"{URL_TYPE.get(b['type'], b['type'])}/{b['number']}"
                ),
                "summary": summary
                and {
                    "version": summary["version"],
                    "date": summary["date"],
                    "text": summary["text"][:SUMMARY_CHARS],
                    "truncated": len(summary["text"]) > SUMMARY_CHARS,
                },
                "votes": votes,
                "closest_margin": closest,
                "party_line": party_line,
                "contested": closest <= CLOSE or party_line,
            }
        )
    bills.sort(key=lambda x: x["latest_action"]["date"], reverse=True)
    return {
        "bills": bills,
        "members": [{k: members[i][k] for k in ("id", "name", "party", "state")} for i in order],
        "close": CLOSE,
        "source": "US House Clerk roll calls; Congress.gov bill status via GovInfo",
        "rule": (
            "Bills and joint resolutions with at least one recorded vote on the bill itself "
            "(passage, suspension, agreeing to the other chamber's version, conference report, "
            "veto override; not procedural votes such as rules or motions to recommit). A bill "
            "counts as contested when, on any of those votes, the losing side had at least 40% "
            "of the yea and nay votes, or most Republicans and most Democrats in the House voted "
            "on opposite sides. Bills are found through House roll calls, so a bill only the "
            "Senate has voted on is not listed yet; Senate counts are as stated in the bill's "
            "official actions. What a bill would change is the Congressional Research "
            "Service's summary of the latest version it has summarized, quoted as published. "
            "Member-by-member votes are the House Clerk's roll calls; senate.gov does not allow "
            "automated access, so Senate votes are shown as totals only."
        ),
    }


BUILDERS["contested_bills"] = contested_bills


SPENDING = re.compile(r"appropriation|rescission|reconciliation|debt limit", re.I)


def spending_laws(store: Store, today: date) -> dict:
    """Which party's votes carried the bills that set federal spending."""
    bills = [
        b
        for b in contested_bills(store, today)["bills"]
        if SPENDING.search(f"{b['title']} {b['official_title']}")
        or b["policy_area"] == "Economics and Public Finance"
    ]
    for b in bills:
        b.pop("summary", None)
        for v in b["votes"]:
            v.pop("codes", None)
    return {
        "bills": bills,
        "source": "US House Clerk roll calls; Congress.gov bill status via GovInfo",
        "rule": (
            "Spending bills are bills with a recorded vote on the bill itself whose title "
            "mentions appropriations, rescissions, reconciliation or the debt limit, or that "
            "Congress.gov files under Economics and Public Finance. For each, the House's "
            "deciding vote is broken down by party from the Clerk's roll call, and the majority "
            "party is the one the Clerk records for that vote. Senate votes are totals as "
            "stated in the bill's official actions, without a party breakdown. A yes vote is "
            "a vote for the bill as it stood then, not for every provision in it."
        ),
    }


def member_votes(store: Store, today: date) -> dict:
    # The member list and their votes ride on the contested_bills panel; the site reads them
    # from there rather than shipping them twice.
    return {
        "source": "US House Clerk roll calls",
        "rule": (
            "Each representative's recorded vote on the House's deciding votes on contested "
            'bills (see the rule above). "With party" means the member voted the same way as '
            "most members of their party who voted yea or nay. Present and not voting are "
            "shown but not counted either way. The House only; senate.gov does not allow "
            "automated access to its member-by-member votes."
        ),
    }


BUILDERS["spending_laws"] = spending_laws
BUILDERS["member_votes"] = member_votes
