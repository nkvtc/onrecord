"""Storage: content-addressed raw files on disk + a SQLite index of derived records.

Raw bodies live at data/raw/<source>/<sha[:2]>/<sha>.<ext> and are never modified.
data/manifest.jsonl is an append-only log of every document version we've fetched and
which topics it belongs to. raw/ + manifest.jsonl are the archive (committed to the
`data` git branch); the SQLite database is a disposable index built from them with
`onrecord rebuild`.

When a source re-serves a document with different bytes, we keep both and bump
`version`. "This official document was quietly edited after publication" is itself
a fact worth surfacing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import ParseResult, RawDocument

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    version       INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    url           TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    title         TEXT,
    jurisdiction  TEXT,
    publisher     TEXT,
    doc_type      TEXT,
    published_on  TEXT,
    canonical_url TEXT,
    citation      TEXT,
    extra_json    TEXT,
    UNIQUE (source, source_id, sha256)
);
CREATE INDEX IF NOT EXISTS documents_published ON documents (published_on);

-- Topic membership is per source document (all its versions), not per version.
CREATE TABLE IF NOT EXISTS document_topics (
    source    TEXT NOT NULL,
    source_id TEXT NOT NULL,
    topic     TEXT NOT NULL,
    PRIMARY KEY (source, source_id, topic)
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents (id),
    kind         TEXT NOT NULL,
    on_date      TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    actor        TEXT NOT NULL,
    title        TEXT NOT NULL,
    locator      TEXT NOT NULL,
    extracted_by TEXT NOT NULL,
    subject      TEXT,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS events_on ON events (on_date);

CREATE TABLE IF NOT EXISTS claims (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents (id),
    speaker      TEXT NOT NULL,
    said_on      TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    text         TEXT NOT NULL,
    locator      TEXT NOT NULL,
    extracted_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS claims_on ON claims (said_on);

CREATE TABLE IF NOT EXISTS series (
    series_id TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    unit      TEXT NOT NULL
);

-- released_at is part of the key so statistical revisions are kept, not overwritten.
CREATE TABLE IF NOT EXISTS observations (
    series_id   TEXT NOT NULL REFERENCES series (series_id),
    period      TEXT NOT NULL,
    value       REAL NOT NULL,
    released_at TEXT NOT NULL DEFAULT '',
    document_id INTEGER NOT NULL REFERENCES documents (id),
    PRIMARY KEY (series_id, period, released_at)
);

CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents (id),
    kind         TEXT NOT NULL,
    payer        TEXT NOT NULL,
    payer_type   TEXT NOT NULL,
    payee        TEXT NOT NULL,
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL,
    on_date      TEXT NOT NULL,
    locator      TEXT NOT NULL,
    extracted_by TEXT NOT NULL,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS transactions_payer ON transactions (payer);
"""

EXTENSIONS = {
    "application/json": "json",
    "text/plain": "txt",
    "text/html": "html",
    "text/csv": "csv",
}

# Manifest entries written before topics existed all came from the first topic.
LEGACY_TOPIC = "us-canada-trade"


def _iso(v):
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.data_dir / "onrecord.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # -- raw ---------------------------------------------------------------

    def raw_path(self, source: str, sha256: str, content_type: str) -> Path:
        ext = EXTENSIONS.get(content_type.split(";")[0], "bin")
        return self.raw_dir / source / sha256[:2] / f"{sha256}.{ext}"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "manifest.jsonl"

    def manifest(self):
        if not self.manifest_path.exists():
            return
        with self.manifest_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)

    def _append_manifest(self, entry: dict) -> None:
        with self.manifest_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_raw(self, row) -> RawDocument:
        path = self.raw_path(row["source"], row["sha256"], row["content_type"])
        return RawDocument(
            source=row["source"],
            source_id=row["source_id"],
            url=row["url"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            content_type=row["content_type"],
            body=path.read_bytes(),
        )

    # -- ingest ------------------------------------------------------------

    def tag(self, source: str, source_id: str, topic: str, record: bool = True) -> bool:
        """Mark a source document as part of a topic. Returns True if the tag is new."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO document_topics (source, source_id, topic) VALUES (?,?,?)",
            (source, source_id, topic),
        )
        self.db.commit()
        is_new = cur.rowcount > 0
        if is_new and record:
            self._append_manifest({"tag": topic, "source": source, "source_id": source_id})
        return is_new

    def ingest(
        self,
        raw: RawDocument,
        parsed: ParseResult,
        topic: str | None = None,
        record: bool = True,
    ) -> tuple[int, bool]:
        """Store a raw document and its parsed records. Returns (document_id, is_new).

        New documents are appended to manifest.jsonl (unless replaying it), which
        together with raw/ is everything needed to rebuild the database.
        """
        sha = raw.sha256
        existing = self.db.execute(
            "SELECT id FROM documents WHERE source=? AND source_id=? AND sha256=?",
            (raw.source, raw.source_id, sha),
        ).fetchone()
        if existing:
            if topic:
                self.tag(raw.source, raw.source_id, topic, record)
            return existing["id"], False

        path = self.raw_path(raw.source, sha, raw.content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw.body)

        (prev,) = self.db.execute(
            "SELECT COALESCE(MAX(version), 0) FROM documents WHERE source=? AND source_id=?",
            (raw.source, raw.source_id),
        ).fetchone()
        m = parsed.meta
        cur = self.db.execute(
            """INSERT INTO documents (source, source_id, version, sha256, url, content_type,
                   fetched_at, title, jurisdiction, publisher, doc_type, published_on,
                   canonical_url, citation, extra_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                raw.source,
                raw.source_id,
                prev + 1,
                sha,
                raw.url,
                raw.content_type,
                _iso(raw.fetched_at),
                m.title,
                m.jurisdiction,
                m.publisher,
                m.doc_type,
                _iso(m.published_on),
                m.canonical_url,
                m.citation,
                json.dumps(m.extra, sort_keys=True),
            ),
        )
        doc_id = cur.lastrowid
        self._write_derived(doc_id, parsed)
        if record:
            self._append_manifest(
                {
                    "source": raw.source,
                    "source_id": raw.source_id,
                    "version": prev + 1,
                    "sha256": sha,
                    "url": raw.url,
                    "content_type": raw.content_type,
                    "fetched_at": _iso(raw.fetched_at),
                    "topic": topic,
                }
            )
        if topic:
            # The manifest entry above already records the topic for this version.
            self.tag(raw.source, raw.source_id, topic, record=False)
        self.db.commit()
        return doc_id, True

    def replace_derived(self, document_id: int, parsed: ParseResult) -> None:
        """Re-parse path: swap out everything derived from one document, metadata included."""
        m = parsed.meta
        self.db.execute(
            """UPDATE documents SET title=?, jurisdiction=?, publisher=?, doc_type=?,
                   published_on=?, canonical_url=?, citation=?, extra_json=? WHERE id=?""",
            (
                m.title,
                m.jurisdiction,
                m.publisher,
                m.doc_type,
                _iso(m.published_on),
                m.canonical_url,
                m.citation,
                json.dumps(m.extra, sort_keys=True),
                document_id,
            ),
        )
        for table in ("events", "claims", "observations", "transactions"):
            self.db.execute(f"DELETE FROM {table} WHERE document_id=?", (document_id,))
        self._write_derived(document_id, parsed)
        self.db.commit()

    def _write_derived(self, doc_id: int, parsed: ParseResult) -> None:
        for e in parsed.events:
            self.db.execute(
                """INSERT INTO events (document_id, kind, on_date, jurisdiction, actor, title,
                       locator, extracted_by, subject, details_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    e.kind,
                    _iso(e.on),
                    e.jurisdiction,
                    e.actor,
                    e.title,
                    e.locator,
                    e.extracted_by,
                    e.subject,
                    json.dumps(e.details, sort_keys=True, ensure_ascii=False)
                    if e.details
                    else None,
                ),
            )
        for c in parsed.claims:
            self.db.execute(
                """INSERT INTO claims (document_id, speaker, said_on, jurisdiction, text,
                       locator, extracted_by) VALUES (?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    c.speaker,
                    _iso(c.said_on),
                    c.jurisdiction,
                    c.text,
                    c.locator,
                    c.extracted_by,
                ),
            )
        for o in parsed.observations:
            self.db.execute(
                "INSERT OR IGNORE INTO series (series_id, label, unit) VALUES (?,?,?)",
                (o.series_id, o.series_label, o.unit),
            )
            self.db.execute(
                """INSERT OR REPLACE INTO observations
                       (series_id, period, value, released_at, document_id)
                   VALUES (?,?,?,?,?)""",
                (o.series_id, _iso(o.period), o.value, o.released_at or "", doc_id),
            )
        for t in parsed.transactions:
            self.db.execute(
                """INSERT INTO transactions (document_id, kind, payer, payer_type, payee,
                       amount, currency, on_date, locator, extracted_by, details_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    t.kind,
                    t.payer,
                    t.payer_type,
                    t.payee,
                    t.amount,
                    t.currency,
                    _iso(t.on),
                    t.locator,
                    t.extracted_by,
                    json.dumps(t.details, sort_keys=True, ensure_ascii=False)
                    if t.details
                    else None,
                ),
            )

    def documents(self, source: str | None = None):
        q = "SELECT * FROM documents"
        args: tuple = ()
        if source:
            q += " WHERE source=?"
            args = (source,)
        return self.db.execute(q + " ORDER BY id", args).fetchall()

    def topic_documents(self, topic: str):
        """Latest version of every document in a topic."""
        return self.db.execute(
            """SELECT d.* FROM documents d
               JOIN document_topics t ON t.source = d.source AND t.source_id = d.source_id
               WHERE t.topic = ? AND d.version = (
                   SELECT MAX(version) FROM documents
                   WHERE source = d.source AND source_id = d.source_id)
               ORDER BY d.id""",
            (topic,),
        ).fetchall()

    def close(self) -> None:
        self.db.close()
