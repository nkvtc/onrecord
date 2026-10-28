"""Rules every adapter must follow. A new adapter gets these checks for free:
add its module, register it, drop at least one real response into tests/fixtures/<name>/.
"""

from datetime import date

import pytest

from onrecord.adapters import ADAPTERS
from onrecord.models import EVENT_KINDS

from .conftest import fixture_names, load_fixture

CASES = [(name, f) for name in ADAPTERS for f in fixture_names(name)]


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_every_adapter_has_fixtures(name):
    assert fixture_names(name), f"add a real response to tests/fixtures/{name}/"


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_adapter_declares_itself(name):
    cls = ADAPTERS[name]
    assert cls.name == name
    assert cls.jurisdiction and cls.description


@pytest.mark.parametrize(("name", "fixture_name"), CASES)
def test_parse_output_is_sourced(name, fixture_name):
    cls = ADAPTERS[name]
    result = cls.parse(load_fixture(name, fixture_name))

    assert result.meta.title
    assert result.meta.canonical_url.startswith("https://")
    assert result.events or result.claims or result.observations or result.transactions, (
        "parsed nothing"
    )

    for e in result.events:
        assert e.kind in EVENT_KINDS
        assert isinstance(e.on, date)
        assert e.locator, "every event must say where in the source it came from"
        assert e.extracted_by == cls.extracted_by()
    for c in result.claims:
        assert c.text and c.speaker and c.locator
    for o in result.observations:
        assert o.series_id and o.unit and o.series_label
    for t in result.transactions:
        assert t.payer and t.payee and t.locator and t.currency
        assert "street" not in t.details, "never republish street addresses"


@pytest.mark.parametrize(("name", "fixture_name"), CASES)
def test_parse_is_deterministic(name, fixture_name):
    cls = ADAPTERS[name]
    raw = load_fixture(name, fixture_name)
    assert cls.parse(raw) == cls.parse(raw)
