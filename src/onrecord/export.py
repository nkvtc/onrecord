"""Export the database as static JSON for the website (and anyone else).

The site is plain files on free static hosting, so "the API" for now is these JSON
files plus the SQLite database itself, which can be queried in the browser via
Datasette Lite with zero servers.

Layout:
    data/topics.json               every topic: title, presentation config, counts
    data/<topic>/timeline.json     dated items (one per document, or per person for lists)
    data/<topic>/series.json       statistical series used by the topic
    data/<topic>/money.json        reported transactions (donations, refunds)
    data/meta.json                 build time and global counts
    data/onrecord.sqlite           everything
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .store import Store
from .topics import Topic

# Which event date best answers "when did this happen?", in order of preference.
# Effective dates come last: they can be in the future, and the item shows them anyway.
PRIMARY_EVENT = ("signed", "adopted", "proposed", "published", "announced", "effective")


def _event_json(e) -> dict:
    out = {"kind": e["kind"], "on": e["on_date"], "actor": e["actor"], "locator": e["locator"]}
    if e["details_json"]:
        out["details"] = json.loads(e["details_json"])
    return out


def build_timeline(store: Store, topic: str) -> list[dict]:
    db = store.db
    items = []
    for doc in store.topic_documents(topic):
        extra = json.loads(doc["extra_json"] or "{}")
        events = db.execute(
            "SELECT * FROM events WHERE document_id=? ORDER BY on_date, id", (doc["id"],)
        ).fetchall()
        claims = db.execute(
            "SELECT speaker, said_on, text, locator FROM claims WHERE document_id=?",
            (doc["id"],),
        ).fetchall()
        base = {
            "jurisdiction": doc["jurisdiction"],
            "publisher": doc["publisher"],
            "citation": doc["citation"],
            "source": doc["source"],
            "sha256": doc["sha256"],
            "version": doc["version"],
        }

        if extra.get("itemize_events"):
            # A list document (e.g. the clemency page): every entry is its own item.
            for n, e in enumerate(events):
                ev = _event_json(e)
                d = ev.get("details", {})
                summary = "; ".join(
                    f"{k}: {d[k]}" for k in ("offense", "sentence", "district", "note") if d.get(k)
                )
                items.append(
                    {
                        **base,
                        "id": f"{doc['source']}:{doc['source_id']}#{n}",
                        "date": e["on_date"],
                        "kind": "action",
                        "doc_type": e["kind"],
                        "title": e["title"],
                        "subject": e["subject"],
                        "url": d.get("warrant_url")
                        or d.get("document_url")
                        or doc["canonical_url"],
                        "summary": summary or None,
                        "events": [ev],
                    }
                )
            continue

        if not events and not claims:
            continue
        if events:
            by_kind = {e["kind"]: e["on_date"] for e in events}
            when = next((by_kind[k] for k in PRIMARY_EVENT if k in by_kind), events[0]["on_date"])
            kind = "action"
        else:
            when = claims[0]["said_on"]
            kind = "statement"
        items.append(
            {
                **base,
                "id": f"{doc['source']}:{doc['source_id']}",
                "date": when,
                "kind": kind,
                "doc_type": doc["doc_type"],
                "title": doc["title"],
                "url": doc["canonical_url"],
                "summary": extra.get("abstract") or (claims[0]["text"] if claims else None),
                "events": [_event_json(e) for e in events],
            }
        )
    items.sort(key=lambda i: (i["date"], i["id"]), reverse=True)
    return items


def build_series(store: Store, topic: str) -> dict:
    out = {}
    doc_ids = [d["id"] for d in store.topic_documents(topic)]
    if not doc_ids:
        return out
    marks = ",".join("?" * len(doc_ids))
    series_ids = [
        r[0]
        for r in store.db.execute(
            f"SELECT DISTINCT series_id FROM observations WHERE document_id IN ({marks})", doc_ids
        )
    ]
    for sid in sorted(series_ids):
        s = store.db.execute("SELECT * FROM series WHERE series_id=?", (sid,)).fetchone()
        # Latest release wins for each period; earlier releases are kept in the DB.
        rows = store.db.execute(
            """SELECT period, value FROM observations o
               WHERE series_id=? AND released_at = (
                   SELECT MAX(released_at) FROM observations
                   WHERE series_id=o.series_id AND period=o.period)
               ORDER BY period""",
            (sid,),
        ).fetchall()
        out[sid] = {
            "label": s["label"],
            "unit": s["unit"],
            "points": [[r["period"], r["value"]] for r in rows],
        }
    return out


def build_money(store: Store, topic: str) -> dict:
    """Transactions from the current filing of each report.

    Filers amend reports; each amendment restates the whole report. Only the latest
    amendment per (filer, report type) is used, or every donation would be counted twice.
    """
    current: dict[tuple, dict] = {}
    for doc in store.topic_documents(topic):
        extra = json.loads(doc["extra_json"] or "{}")
        if "report_type" not in extra:
            continue
        key = (extra.get("committee_id"), extra["report_type"])
        file_no = int(doc["source_id"].split(":")[-1])
        if key not in current or file_no > current[key]["file_no"]:
            current[key] = {"file_no": file_no, "doc": doc, "extra": extra}

    reports, rows = [], []
    for r in sorted(current.values(), key=lambda r: r["file_no"]):
        doc = r["doc"]
        reports.append(
            {
                "title": doc["title"],
                "filer": doc["publisher"],
                "url": doc["canonical_url"],
                "citation": doc["citation"],
                "received": doc["published_on"],
                "totals": {
                    k: r["extra"].get(k)
                    for k in ("total_donations", "total_refunds", "net_donations")
                },
                "sha256": doc["sha256"],
            }
        )
        for t in store.db.execute(
            "SELECT * FROM transactions WHERE document_id=? ORDER BY amount DESC, payer",
            (doc["id"],),
        ):
            details = json.loads(t["details_json"] or "{}")
            rows.append(
                {
                    "kind": t["kind"],
                    "payer": t["payer"],
                    "payer_type": t["payer_type"],
                    "payee": t["payee"],
                    "amount": t["amount"],
                    "currency": t["currency"],
                    "date": t["on_date"],
                    "place": ", ".join(details[k] for k in ("city", "state") if details.get(k)),
                    "locator": t["locator"],
                    "url": doc["canonical_url"],
                }
            )
    return {"reports": reports, "transactions": rows}


def export(store: Store, out_dir: Path, topics: list[Topic], site_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir)
    if site_dir and Path(site_dir).exists():
        shutil.copytree(site_dir, out_dir, dirs_exist_ok=True)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    def dump(path: Path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    index = []
    for topic in sorted(topics, key=lambda t: (t.site.get("order", 99), t.id)):
        timeline = build_timeline(store, topic.id)
        series = build_series(store, topic.id)
        money = build_money(store, topic.id)
        dump(data_dir / topic.id / "timeline.json", timeline)
        dump(data_dir / topic.id / "series.json", series)
        dump(data_dir / topic.id / "money.json", money)
        index.append(
            {
                "id": topic.id,
                "title": topic.title,
                "since": topic.since.isoformat(),
                "description": topic.description.strip(),
                "site": topic.site,
                "counts": {
                    "documents": len(store.topic_documents(topic.id)),
                    "items": len(timeline),
                    "series": len(series),
                    "transactions": len(money["transactions"]),
                },
            }
        )

    counts = {
        t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("documents", "events", "claims", "observations", "transactions")
    }
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": counts,
        "sources": [
            r[0] for r in store.db.execute("SELECT DISTINCT source FROM documents ORDER BY source")
        ],
    }
    dump(data_dir / "topics.json", index)
    dump(data_dir / "meta.json", meta)
    store.db.commit()
    # Ship the whole database too: anyone can query it with SQL in their browser.
    shutil.copyfile(store.data_dir / "onrecord.sqlite", data_dir / "onrecord.sqlite")
    return meta
