from datetime import UTC, datetime
from pathlib import Path

import pytest

from onrecord.models import RawDocument

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(source: str, name: str) -> RawDocument:
    path = FIXTURES / source / name
    return RawDocument(
        source=source,
        source_id=path.stem,
        url=f"fixture://{source}/{name}",
        fetched_at=datetime(2026, 10, 21, tzinfo=UTC),
        content_type="application/json",
        body=path.read_bytes(),
    )


@pytest.fixture
def fixture():
    return load_fixture
