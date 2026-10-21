from onrecord.adapters import ADAPTERS
from onrecord.cli import main
from onrecord.store import Store

from .conftest import FIXTURES, load_fixture


def test_rebuild_from_manifest_matches_original(tmp_path):
    store = Store(tmp_path)
    for name in ADAPTERS:
        for path in (FIXTURES / name).glob("*.json"):
            raw = load_fixture(name, path.name)
            store.ingest(raw, ADAPTERS[name].parse(raw))

    def snapshot(s):
        return {
            t: s.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("documents", "events", "claims", "observations")
        }

    before = snapshot(store)
    manifest_lines = store.manifest_path.read_text().splitlines()
    store.close()

    assert main(["--data", str(tmp_path), "rebuild"]) == 0
    rebuilt = Store(tmp_path)
    assert snapshot(rebuilt) == before
    # Replaying must not append to the manifest.
    assert rebuilt.manifest_path.read_text().splitlines() == manifest_lines
