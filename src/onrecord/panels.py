"""Comparison panels: computed views over archived records, each with its counting rule.

A panel is only as fair as the way it counts, so every panel carries a plain-language
`rule` the site prints next to the chart. Change a rule here and the page changes with
it; nothing is hand-entered.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

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
    lists = _latest_docs(store, "doj_clemency")
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
