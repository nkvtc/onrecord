import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from onrecord.models import RawDocument

FIXTURES = Path(__file__).parent / "fixtures"
CONTENT_TYPES = {".json": "application/json", ".html": "text/html", ".txt": "text/plain"}


def fixture_names(source: str) -> list[str]:
    """Real saved responses for an adapter (files starting with "_" are metadata)."""
    return sorted(p.name for p in (FIXTURES / source).glob("*") if not p.name.startswith("_"))


def load_fixture(source: str, name: str) -> RawDocument:
    path = FIXTURES / source / name
    # Optional _sources.json records the real source_id/url for fixtures whose parser
    # needs them (e.g. to resolve relative links). Otherwise the file stem is used.
    sources_file = FIXTURES / source / "_sources.json"
    known = json.loads(sources_file.read_text()).get(name, {}) if sources_file.exists() else {}
    return RawDocument(
        source=source,
        source_id=known.get("source_id", path.stem),
        url=known.get("url", f"fixture://{source}/{name}"),
        fetched_at=datetime(2026, 10, 21, tzinfo=UTC),
        content_type=CONTENT_TYPES[path.suffix],
        body=path.read_bytes(),
    )


@pytest.fixture
def fixture():
    return load_fixture
