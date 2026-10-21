"""Export the database as static JSON for the website (and anyone else).

The site is plain files on free static hosting, so "the API" for now is just these
JSON files plus the SQLite database itself, which can be queried in the browser via
Datasette Lite with zero servers.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .store import Store

# Which event date best answers "when did this happen?", in order of preference.
PRIMARY_EVENT = ("signed", "effective", "published", "announced")


def build_timeline(store: Store) -> list[dict]:
    db = store.db
    docs = {r["id"]: r for r in db.execute("SELECT * FROM documents")}
    # Only the latest version of each document goes on the timeline.
    latest = {}
    for r in docs.values():
        key = (r["source"], r["source_id"])
        if key not in latest or r["version"] > latest[key]["version"]:
            latest[key] = r

    items = []
    for doc in latest.values():
        events = db.execute(
            "SELECT kind, on_date, actor, locator FROM events WHERE document_id=? ORDER BY on_date",
            (doc["id"],),
        ).fetchall()
        claims = db.execute(
            "SELECT speaker, said_on, text, locator FROM claims WHERE document_id=?",
            (doc["id"],),
        ).fetchall()
        if not events and not claims:
            continue
        if events:
            by_kind = {e["kind"]: e["on_date"] for e in events}
            when = next(by_kind[k] for k in PRIMARY_EVENT if k in by_kind)
            kind = "action"
        else:
            when = claims[0]["said_on"]
            kind = "statement"
        extra = json.loads(doc["extra_json"] or "{}")
        items.append(
            {
                "id": f"{doc['source']}:{doc['source_id']}",
                "date": when,
                "kind": kind,
                "jurisdiction": doc["jurisdiction"],
                "doc_type": doc["doc_type"],
                "publisher": doc["publisher"],
                "title": doc["title"],
                "url": doc["canonical_url"],
                "citation": doc["citation"],
                "summary": extra.get("abstract") or (claims[0]["text"] if claims else None),
                "events": [
                    {
                        "kind": e["kind"],
                        "on": e["on_date"],
                        "actor": e["actor"],
                        "locator": e["locator"],
                    }
                    for e in events
                ],
                "source": doc["source"],
                "sha256": doc["sha256"],
                "version": doc["version"],
            }
        )
    items.sort(key=lambda i: (i["date"], i["id"]), reverse=True)
    return items


def build_series(store: Store) -> dict:
    out = {}
    for s in store.db.execute("SELECT * FROM series ORDER BY series_id"):
        # Latest release wins for each period; earlier releases are kept in the DB.
        rows = store.db.execute(
            """SELECT period, value, released_at FROM observations o
               WHERE series_id=? AND released_at = (
                   SELECT MAX(released_at) FROM observations
                   WHERE series_id=o.series_id AND period=o.period)
               ORDER BY period""",
            (s["series_id"],),
        ).fetchall()
        out[s["series_id"]] = {
            "label": s["label"],
            "unit": s["unit"],
            "points": [[r["period"], r["value"]] for r in rows],
        }
    return out


def export(store: Store, out_dir: Path, site_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir)
    if site_dir and Path(site_dir).exists():
        shutil.copytree(site_dir, out_dir, dirs_exist_ok=True)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    timeline = build_timeline(store)
    series = build_series(store)
    counts = {
        t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("documents", "events", "claims", "observations")
    }
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": counts,
        "sources": [
            r[0] for r in store.db.execute("SELECT DISTINCT source FROM documents ORDER BY source")
        ],
    }

    def dump(name, obj):
        (data_dir / name).write_text(
            json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    dump("timeline.json", timeline)
    dump("series.json", series)
    dump("meta.json", meta)
    store.db.commit()
    # Ship the whole database too: anyone can query it with SQL in their browser.
    shutil.copyfile(store.data_dir / "onrecord.sqlite", data_dir / "onrecord.sqlite")
    return meta
