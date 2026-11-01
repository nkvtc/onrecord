"""Follow the money: Treasury receipts, USAspending snapshots, GAO reports, and panels."""

from datetime import date

from onrecord.adapters.gao_reports import GaoReports
from onrecord.adapters.treasury_mts import TreasuryMts
from onrecord.adapters.usaspending import UsaSpending
from onrecord.panels import monthly_revenue, spending_map, top_contractors
from onrecord.store import Store


def test_customs_duties_are_net_and_can_be_negative(fixture):
    r = TreasuryMts.parse(fixture("treasury_mts", "mts9_customs_duties.json"))
    by_month = {o.period: o.value for o in r.observations}
    assert r.observations[0].series_id == "treasury:mts9:customs_duties"
    assert r.observations[0].unit == "USD millions"
    assert date(2015, 3, 1) in by_month  # history back to 2015
    # Refunds exceeded collections in June 2026: kept negative, not dropped or clipped.
    assert by_month[date(2026, 6, 1)] < -25_000
    total_2025 = sum(v for d, v in by_month.items() if d.year == 2025)
    assert 263_000 < total_2025 < 265_000


def test_usaspending_state_snapshot(fixture):
    r = UsaSpending.parse(fixture("usaspending", "geo_state_FY2026.json"))
    rows = {row["code"]: row for row in r.meta.extra["rows"]}
    assert r.meta.extra["kind"] == "geo_state" and r.meta.extra["fiscal_year"] == 2026
    assert r.meta.published_on == date(2026, 9, 30)  # end of FY2026
    nd = rows["ND"]
    assert round(nd["amount"] / nd["population"]) == round(nd["per_capita"])


def test_usaspending_agency_breakdown_explains_outlier(fixture):
    r = UsaSpending.parse(fixture("usaspending", "agencies_ND_FY2026.json"))
    rows = r.meta.extra["rows"]
    assert r.meta.extra["state"] == "ND"
    assert rows[0]["name"] == "Department of Health and Human Services"
    assert rows[0]["amount"] / sum(x["amount"] for x in rows) > 0.9


def test_contractors_kept_as_reported(fixture):
    r = UsaSpending.parse(fixture("usaspending", "contractors_FY2026.json"))
    names = [row["name"] for row in r.meta.extra["rows"]]
    # Separate registrations of one company are not merged.
    assert names.count("LOCKHEED MARTIN CORPORATION") == 2


def test_gao_item_is_a_claim(fixture):
    r = GaoReports.parse(fixture("gao_reports", "gao_item.xml"))
    (claim,) = r.claims
    assert claim.speaker == "US Government Accountability Office"
    assert claim.said_on == date(2026, 10, 26)
    assert r.meta.canonical_url == "https://www.gao.gov/products/e16067"
    assert r.meta.citation == "GAO E16067"


def test_money_panels(tmp_path, fixture):
    store = Store(tmp_path)
    for adapter, src, name in (
        (TreasuryMts, "treasury_mts", "mts9_customs_duties.json"),
        (UsaSpending, "usaspending", "geo_state_FY2026.json"),
        (UsaSpending, "usaspending", "agencies_ND_FY2026.json"),
        (UsaSpending, "usaspending", "contractors_FY2026.json"),
    ):
        raw = fixture(src, name)
        store.ingest(raw, adapter.parse(raw), topic="m")
    today = date(2026, 11, 1)

    rev = monthly_revenue(store, today, series="treasury:mts9:customs_duties")
    assert [p for p, _ in rev["negative_months"]] == ["2026-05-01", "2026-06-01", "2026-07-01"]
    years = {y["year"]: y for y in rev["years"]}
    assert years["2026"]["months"] == 9 and years["2025"]["months"] == 12
    assert "refunds exceeded collections" in rev["rule"]

    m = spending_map(store, today)
    assert list(m["states"]) == ["2026"] and "ND" in m["agencies"]["2026"]
    assert "place of performance" in m["rule"]

    c = top_contractors(store, today)
    assert c["fiscal_year"] == 2026 and len(c["rows"]) == 25
