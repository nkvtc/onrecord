"""Where the money goes: Treasury budget tables, agency profiles, improper payments."""

from datetime import date

from onrecord.adapters.payment_accuracy import PaymentAccuracy
from onrecord.adapters.treasury_budget import TreasuryBudget
from onrecord.adapters.usaspending_agencies import UsaSpendingAgencies
from onrecord.panels import (
    agency_outlays,
    budget_functions,
    improper_payments,
    money_flow,
    receipts_outlays,
)
from onrecord.store import Store


def test_functions_and_totals_by_fiscal_year(fixture):
    r = TreasuryBudget.parse(fixture("treasury_budget", "mts9_FY2026.json"))
    x = r.meta.extra
    assert (x["fiscal_year"], x["months"], x["through"]) == (2026, 12, "2026-09-30")
    out = {row["name"]: row["amount"] for row in x["rows"] if row["section"] == "outlays"}
    # Lines add up to the published total; negative lines are kept, not dropped.
    assert abs(sum(out.values()) - x["totals"]["outlays"]) < 1
    assert out["Commerce and Housing Credit"] < 0
    assert out["Net Interest"] > out["National Defense"]
    sub = [row for row in x["rows"] if row.get("group")]
    assert {row["group"] for row in sub} == {"Social Insurance and Retirement Receipts"}
    assert 5.3e12 < x["totals"]["receipts"] < 5.5e12


def test_agency_table_keeps_bureaus_and_deficit(fixture):
    x = TreasuryBudget.parse(fixture("treasury_budget", "mts5_FY2026.json")).meta.extra
    agencies = {a["name"]: a for a in x["rows"]}
    treasury = {b["name"]: b["amount"] for b in agencies["Department of the Treasury"]["bureaus"]}
    assert treasury["Interest on the Public Debt"] > 1e12
    assert abs(sum(a["amount"] for a in x["rows"]) - x["totals"]["outlays"]) < 1
    assert -2.1e12 < x["totals"]["surplus_or_deficit"] < -1.9e12


def test_agency_profile_has_mission_and_functions(fixture):
    x = UsaSpendingAgencies.parse(fixture("usaspending_agencies", "agency_075_FY2026.json"))
    e = x.meta.extra
    assert e["name"] == "Department of Health and Human Services"
    assert e["mission"].startswith("It is the mission")
    assert e["rows"][0]["name"] == "Medicare"
    assert x.meta.canonical_url.endswith("/agency/department-of-health-and-human-services")


def test_improper_payments_as_published(fixture):
    x = PaymentAccuracy.parse(fixture("payment_accuracy", "FY2025_Dataset.xlsx")).meta.extra
    fy24 = [r for r in x["rows"] if r["fiscal_year"] == 2024 and r["improper_and_unknown"]]
    # OMB's government-wide FY2024 figure is $162 billion.
    assert 161_000 < sum(r["improper_and_unknown"] for r in fy24) < 162_500
    assert {r["fiscal_year"] for r in x["rows"]} >= set(range(2004, 2026))


def test_budget_panels(tmp_path, fixture):
    store = Store(tmp_path)
    for adapter, src, name in (
        (TreasuryBudget, "treasury_budget", "mts9_FY2015.json"),
        (TreasuryBudget, "treasury_budget", "mts9_FY2026.json"),
        (TreasuryBudget, "treasury_budget", "mts5_FY2026.json"),
        (UsaSpendingAgencies, "usaspending_agencies", "agency_075_FY2026.json"),
        (PaymentAccuracy, "payment_accuracy", "FY2025_Dataset.xlsx"),
    ):
        raw = fixture(src, name)
        store.ingest(raw, adapter.parse(raw), topic="b")
    today = date(2026, 11, 1)

    f = budget_functions(store, today)
    assert [y["fy"] for y in f["years"]] == [2015, 2026]
    assert f["years"][1]["lines"][0]["name"] == "Social Security"

    ro = receipts_outlays(store, today)
    assert 1.9e12 < ro["years"][1]["deficit"] < 2.1e12

    mf = money_flow(store, today)["years"][1]
    left = sum(r["amount"] for r in mf["sources"]) + mf["borrowed"] + mf["came_back"]
    right = sum(r["amount"] for r in mf["uses"]) + mf["surplus"]
    assert abs(left - right) / right < 0.01  # both sides of the flow balance

    a = agency_outlays(store, today)
    hhs = next(x for x in a["years"][0]["agencies"] if x["name"].endswith("Human Services"))
    assert hhs["profile"] == "Department of Health and Human Services"
    assert "Medicare" in [fn["name"] for fn in a["profiles"][hhs["profile"]]["functions"]]

    ip = improper_payments(store, today)
    assert ip["fiscal_year"] == 2025 and ip["programs"][0]["improper_and_unknown"] > 10_000
    assert "not a fraud estimate" in ip["rule"]
