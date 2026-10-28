from onrecord.adapters import ADAPTERS
from onrecord.cli import main
from onrecord.store import Store

from .conftest import fixture_names, load_fixture


def test_rebuild_from_manifest_matches_original(tmp_path):
    store = Store(tmp_path)
    for name in ADAPTERS:
        for f in fixture_names(name):
            raw = load_fixture(name, f)
            store.ingest(raw, ADAPTERS[name].parse(raw), topic="t1")

    def snapshot(s):
        return {
            t: s.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in (
                "documents",
                "events",
                "claims",
                "observations",
                "transactions",
                "document_topics",
            )
        }

    before = snapshot(store)
    manifest_lines = store.manifest_path.read_text().splitlines()
    store.close()

    assert main(["--data", str(tmp_path), "rebuild"]) == 0
    rebuilt = Store(tmp_path)
    assert snapshot(rebuilt) == before
    # Replaying must not append to the manifest.
    assert rebuilt.manifest_path.read_text().splitlines() == manifest_lines


def test_rebuild_refuses_altered_archive(tmp_path, fixture):
    from onrecord.adapters.canada_news import CanadaNews

    store = Store(tmp_path)
    name = "canada-announces-155b-tariff-package-in-response-to-unjustified-us-tariffs.html.json"
    raw = fixture("canada_news", name)
    store.ingest(raw, CanadaNews.parse(raw), topic="t")
    path = store.raw_path(raw.source, raw.sha256, raw.content_type)
    store.close()
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))  # what git autocrlf does
    assert main(["--data", str(tmp_path), "rebuild"]) == 1
