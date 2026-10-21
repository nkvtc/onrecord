import json
from dataclasses import replace

from onrecord.adapters.federal_register import FederalRegister
from onrecord.adapters.statcan_trade import StatcanTrade
from onrecord.export import build_series, build_timeline
from onrecord.store import Store


def test_ingest_is_idempotent(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")
    doc_id, new = store.ingest(raw, FederalRegister.parse(raw))
    again, new_again = store.ingest(raw, FederalRegister.parse(raw))
    assert new and not new_again and doc_id == again
    assert store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
    assert store.read_raw(store.documents()[0]).body == raw.body


def test_changed_document_becomes_new_version(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")
    store.ingest(raw, FederalRegister.parse(raw))

    edited = json.loads(raw.body)
    edited["title"] += " (corrected)"
    raw2 = replace(raw, body=json.dumps(edited).encode())
    store.ingest(raw2, FederalRegister.parse(raw2))

    versions = [r["version"] for r in store.documents()]
    assert versions == [1, 2]
    # The timeline shows only the latest version.
    (item,) = build_timeline(store)
    assert item["title"].endswith("(corrected)") and item["version"] == 2


def test_reparse_replaces_rather_than_duplicates(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")
    store.ingest(raw, FederalRegister.parse(raw))
    row = store.documents()[0]
    store.replace_derived(row["id"], FederalRegister.parse(store.read_raw(row)))
    assert store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2


def test_timeline_dates_actions_by_signing(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")
    store.ingest(raw, FederalRegister.parse(raw))
    (item,) = build_timeline(store)
    assert item["date"] == "2025-02-01" and item["kind"] == "action"


def test_series_export(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("statcan_trade", "12100011_1.1.2.2.2.0.0.0.0.0.json")
    store.ingest(raw, StatcanTrade.parse(raw))
    (series,) = build_series(store).values()
    assert len(series["points"]) == 48 and series["unit"] == "CAD millions"
