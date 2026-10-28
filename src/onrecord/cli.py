"""Command line: onrecord pull | reparse | export | status | sources"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .adapters import ADAPTERS
from .export import export
from .http import Http
from .store import LEGACY_TOPIC, Store
from .topics import TOPICS_DIR, all_topics

ROOT = Path(__file__).resolve().parents[2]


def cmd_pull(args) -> int:
    store = Store(args.data)
    http = Http()
    topics = [t for t in all_topics(args.topics) if not args.topic or t.id == args.topic]
    if not topics:
        print(f"No topic matching {args.topic!r} in {args.topics}", file=sys.stderr)
        return 2
    failures = 0
    for topic in topics:
        for name, cls in ADAPTERS.items():
            if args.source and name not in args.source:
                continue
            if topic.config(name) is None:
                continue
            if cls.requires_env and not os.environ.get(cls.requires_env):
                print(f"[{topic.id}] {name}: skipped, set {cls.requires_env} to enable")
                continue
            new = seen = 0
            try:
                for raw in cls(http).fetch(topic):
                    _, is_new = store.ingest(raw, cls.parse(raw), topic=topic.id)
                    seen += 1
                    new += is_new
            except Exception as e:  # one broken source must not stop the others
                failures += 1
                print(f"[{topic.id}] {name}: FAILED after {seen} docs: {e!r}", file=sys.stderr)
                continue
            print(f"[{topic.id}] {name}: {seen} documents, {new} new or changed")
    http.close()
    store.close()
    return 1 if failures else 0


def cmd_reparse(args) -> int:
    store = Store(args.data)
    n = 0
    for row in store.documents(args.source):
        cls = ADAPTERS[row["source"]]
        store.replace_derived(row["id"], cls.parse(store.read_raw(row)))
        n += 1
    print(f"Re-parsed {n} documents from the raw archive (no network).")
    return 0


def cmd_rebuild(args) -> int:
    """Recreate the SQLite index from manifest.jsonl + raw/, e.g. on a fresh CI runner."""
    db_path = Path(args.data) / "onrecord.sqlite"
    db_path.unlink(missing_ok=True)
    store = Store(args.data)
    n = 0
    for entry in store.manifest():
        if "tag" in entry:
            store.tag(entry["source"], entry["source_id"], entry["tag"], record=False)
            continue
        raw = store.read_raw(entry)
        if raw.sha256 != entry["sha256"]:
            # Bytes on disk changed since they were archived (e.g. git rewrote line endings).
            # Ingesting them would invent a new "version" of an official document.
            print(
                f"Archive integrity error: {entry['source']}:{entry['source_id']} "
                f"does not match its recorded sha256. Check out the data branch with "
                f"line-ending conversion off (see data/.gitattributes).",
                file=sys.stderr,
            )
            return 1
        topic = entry.get("topic") or LEGACY_TOPIC
        store.ingest(raw, ADAPTERS[raw.source].parse(raw), topic=topic, record=False)
        n += 1
    print(f"Rebuilt database from {n} archived document versions.")
    return 0


def cmd_export(args) -> int:
    store = Store(args.data)
    meta = export(store, args.out, all_topics(args.topics), ROOT / "site")
    print(f"Exported to {args.out}: {meta['counts']}")
    return 0


def cmd_status(args) -> int:
    store = Store(args.data)
    rows = store.db.execute(
        """SELECT source, COUNT(DISTINCT source_id) docs, COUNT(*) versions,
                  MIN(published_on) first, MAX(published_on) last, MAX(fetched_at) fetched
           FROM documents GROUP BY source"""
    ).fetchall()
    for r in rows:
        print(
            f"{r['source']:18} {r['docs']:5} docs  {r['versions']:5} versions  "
            f"{r['first']} .. {r['last']}  last fetch {r['fetched'][:19]}"
        )
    for t in ("events", "claims", "observations", "transactions"):
        print(f"{t:18} {store.db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    return 0


def cmd_sources(args) -> int:
    for name, cls in ADAPTERS.items():
        key = f"  (needs {cls.requires_env})" if cls.requires_env else ""
        print(f"{name:18} {cls.jurisdiction}  {cls.description}{key}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="onrecord")
    p.add_argument("--data", type=Path, default=ROOT / "data", help="data directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    pull = sub.add_parser("pull", help="fetch new documents from sources")
    pull.add_argument("--topic", help="only this topic id")
    pull.add_argument("--source", action="append", help="only this adapter (repeatable)")
    pull.add_argument("--topics", type=Path, default=TOPICS_DIR)
    pull.set_defaults(fn=cmd_pull)

    rp = sub.add_parser("reparse", help="rebuild parsed records from the raw archive")
    rp.add_argument("--source")
    rp.set_defaults(fn=cmd_reparse)

    sub.add_parser("rebuild", help="recreate the database from manifest.jsonl + raw/").set_defaults(
        fn=cmd_rebuild
    )

    ex = sub.add_parser("export", help="write the static site + JSON")
    ex.add_argument("--out", type=Path, default=ROOT / "build")
    ex.add_argument("--topics", type=Path, default=TOPICS_DIR)
    ex.set_defaults(fn=cmd_export)

    sub.add_parser("status", help="what's in the database").set_defaults(fn=cmd_status)
    sub.add_parser("sources", help="list adapters").set_defaults(fn=cmd_sources)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
