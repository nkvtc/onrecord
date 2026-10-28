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
    store.ingest(raw, FederalRegister.parse(raw), topic="t")

    edited = json.loads(raw.body)
    edited["title"] += " (corrected)"
    raw2 = replace(raw, body=json.dumps(edited).encode())
    store.ingest(raw2, FederalRegister.parse(raw2), topic="t")

    versions = [r["version"] for r in store.documents()]
    assert versions == [1, 2]
    # The timeline shows only the latest version.
    (item,) = build_timeline(store, "t")
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
    store.ingest(raw, FederalRegister.parse(raw), topic="t")
    (item,) = build_timeline(store, "t")
    assert item["date"] == "2025-02-01" and item["kind"] == "action"


def test_series_export(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("statcan_trade", "12100011_1.1.2.2.2.0.0.0.0.0.json")
    store.ingest(raw, StatcanTrade.parse(raw), topic="t")
    (series,) = build_series(store, "t").values()
    assert len(series["points"]) == 48 and series["unit"] == "CAD millions"


def test_topics_are_tracked_and_survive_rebuild(tmp_path, fixture):
    from onrecord.cli import main

    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")
    store.ingest(raw, FederalRegister.parse(raw), topic="a")
    # Same document found again by another topic: no new version, just a new tag.
    _, is_new = store.ingest(raw, FederalRegister.parse(raw), topic="b")
    assert not is_new
    assert [len(store.topic_documents(t)) for t in ("a", "b", "c")] == [1, 1, 0]
    lines = store.manifest_path.read_text().splitlines()
    assert len(lines) == 2 and '"tag": "b"' in lines[1]
    store.close()

    assert main(["--data", str(tmp_path), "rebuild"]) == 0
    rebuilt = Store(tmp_path)
    assert [len(rebuilt.topic_documents(t)) for t in ("a", "b")] == [1, 1]


def test_money_export_uses_only_latest_amendment(tmp_path, fixture):
    from onrecord.adapters.fec_form13 import FecForm13
    from onrecord.export import build_money

    store = Store(tmp_path)
    raw = fixture("fec_form13", "C00894162_1910509.txt")
    store.ingest(raw, FecForm13.parse(raw), topic="m")
    # An older amendment of the same report must not be double counted.
    older = replace(raw, source_id="C00894162:1900000", body=raw.body + b"\n")
    store.ingest(older, FecForm13.parse(older), topic="m")
    money = build_money(store, "m")
    assert [r["citation"] for r in money["reports"]] == ["FEC filing 1910509"]
    assert len(money["transactions"]) == 974
