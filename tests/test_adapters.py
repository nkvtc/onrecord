"""Source-specific expectations, checked against real saved responses."""

from datetime import date

from onrecord.adapters.canada_news import CanadaNews
from onrecord.adapters.federal_register import FederalRegister
from onrecord.adapters.statcan_trade import StatcanTrade
from onrecord.topics import Topic


def test_executive_order_signed_and_published(fixture):
    r = FederalRegister.parse(fixture("federal_register", "2025-02406.json"))
    assert r.meta.doc_type == "executive_order"
    assert r.meta.title.startswith("EO 14193:")
    assert r.meta.citation == "90 FR 9113"
    kinds = {e.kind: e for e in r.events}
    assert kinds["signed"].on == date(2025, 2, 1)
    assert kinds["signed"].actor == "Donald Trump"
    assert kinds["published"].on == date(2025, 2, 7)
    # The FR API leaves effective_on empty for this EO even though the text sets one.
    # We must not invent it; full-text extraction is a separate, verified step.
    assert "effective" not in kinds


def test_rule_has_effective_date(fixture):
    r = FederalRegister.parse(fixture("federal_register", "2024-31214.json"))
    assert r.meta.doc_type == "rule"
    kinds = {e.kind: e.on for e in r.events}
    assert kinds == {"published": date(2025, 1, 21), "effective": date(2025, 3, 24)}


def test_news_release_is_a_claim_not_an_event(fixture):
    raw = fixture(
        "canada_news",
        "canada-announces-155b-tariff-package-in-response-to-unjustified-us-tariffs.html.json",
    )
    r = CanadaNews.parse(raw)
    assert r.events == []
    (claim,) = r.claims
    assert claim.speaker == "Department of Finance Canada"
    assert claim.said_on == date(2025, 2, 1)
    assert "$155B" in claim.text


def test_statcan_series(fixture):
    r = StatcanTrade.parse(fixture("statcan_trade", "12100011_1.1.2.2.2.0.0.0.0.0.json"))
    assert len(r.observations) == 48
    first = r.observations[0]
    assert first.period == date(2022, 9, 1)
    assert first.value == 40885.9
    assert first.unit == "CAD millions"
    assert "imports from United States" in first.series_label
    assert "seasonally adjusted" in first.series_label


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.url = "https://example.test"

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, **kwargs):
        return FakeResponse(self.payload)


def test_canada_news_keyword_filter_matches_word_starts():
    when = "2025-03-01T10:00:00-05:00"
    entries = [
        {"title": "New tariffs on steel", "teaser": "", "link": "https://a", "publishedDate": when},
        {
            "title": "Minister refocus.",
            "teaser": "virus.",
            "link": "https://b",
            "publishedDate": when,
        },
    ]
    cfg = {"departments": ["departmentfinance"], "keywords": ["tariff", "u.s."]}
    topic = Topic(id="t", title="t", since=date(2025, 1, 1), sources={"canada_news": cfg})
    got = [r.source_id for r in CanadaNews(FakeHttp({"feed": {"entry": entries}})).fetch(topic)]
    assert got == ["https://a"]
