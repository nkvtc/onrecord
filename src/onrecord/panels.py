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
    return [{**p, **BUILDERS[p["kind"]](store, today)} for p in panels]
