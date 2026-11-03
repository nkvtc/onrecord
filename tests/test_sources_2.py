"""Expectations for the EU, US-trade and accountability sources, on real saved responses."""

from collections import Counter
from datetime import date

from onrecord.adapters.doj_clemency import DojClemency
from onrecord.adapters.eurlex import EurLex
from onrecord.adapters.eurostat_trade import EurostatTrade
from onrecord.adapters.fec_form13 import FecForm13
from onrecord.adapters.fred_trade import FredTrade

CLEMENCY = "clemency-grants-president-donald-j-trump-2025-present.html"


def test_fred_series(fixture):
    r = FredTrade.parse(fixture("fred_trade", "EXPCA.json"))
    first = r.observations[0]
    assert first.series_id == "fred:EXPCA"
    assert first.unit == "USD millions"
    assert first.period == date(2024, 1, 1)
    assert "via FRED" in first.series_label and "not seasonally adjusted" in first.series_label
    assert r.meta.canonical_url == "https://fred.stlouisfed.org/series/EXPCA"


def test_eurostat_series(fixture):
    r = EurostatTrade.parse(fixture("eurostat_trade", "ext_st_eu27_2020sitc_EXP_US.json"))
    assert r.observations[0].series_id == "eurostat:ext_st_eu27_2020sitc:EXP:US"
    assert r.observations[0].unit == "EUR millions"
    assert r.observations[0].period == date(2024, 1, 1)
    periods = [o.period for o in r.observations]
    assert periods == sorted(periods) and len(set(periods)) == len(periods)


def test_eurlex_regulation_is_adopted_by_dg_trade(fixture):
    r = EurLex.parse(fixture("eurlex", "32025R0778.json"))
    (event,) = r.events
    assert event.kind == "adopted"
    assert event.on == date(2025, 4, 14)
    assert r.meta.doc_type == "regulation"
    assert r.meta.publisher == "European Commission (DG Trade)"
    assert "rebalancing" in r.meta.title
    assert " " not in r.meta.title


def test_eurlex_proposal_is_proposed(fixture):
    r = EurLex.parse(fixture("eurlex", "52026PC0485.json"))
    assert r.events[0].kind == "proposed"
    assert r.meta.doc_type == "proposal"


def test_clemency_page(fixture):
    r = DojClemency.parse(fixture("doj_clemency", CLEMENCY))
    kinds = Counter(e.kind for e in r.events)
    named = [e for e in r.events if e.subject]
    assert len(named) == 171
    assert kinds["pardoned"] == 102 and kinds["commuted"] == 15
    # Two grants by proclamation (January 6, 2020 election) have no named individuals.
    proclamations = [e for e in r.events if not e.subject]
    assert len(proclamations) == 2
    assert all(e.kind == "clemency" for e in proclamations)

    ulbricht = next(e for e in named if e.subject == "Ross William Ulbricht")
    assert ulbricht.kind == "pardoned" and ulbricht.on == date(2025, 1, 21)
    assert ulbricht.details["district"] == "Southern District of New York"
    assert ulbricht.details["warrant_url"].startswith("https://www.justice.gov/")
    assert "#21.January.2025.clemency" in ulbricht.locator


def test_mixed_sections_do_not_guess_pardon_or_commutation(fixture):
    r = DojClemency.parse(fixture("doj_clemency", CLEMENCY))
    mixed = [
        e
        for e in r.events
        if e.subject and "Commutation" in e.details["section"] and "Pardon" in e.details["section"]
    ]
    assert mixed and all(e.kind == "clemency" for e in mixed)


def test_fec_form13_matches_filed_totals(fixture):
    r = FecForm13.parse(fixture("fec_form13", "C00894162_1910509.txt"))
    donations = [t for t in r.transactions if t.kind == "donation"]
    refunds = [t for t in r.transactions if t.kind == "refund"]
    assert len(donations) == 946 and len(refunds) == 28
    # The itemized lines add up exactly to the total the committee reported.
    assert round(sum(t.amount for t in donations), 2) == r.meta.extra["total_donations"]
    assert round(sum(t.amount for t in refunds), 2) == r.meta.extra["total_refunds"]
    biggest = max(donations, key=lambda t: t.amount)
    assert biggest.payer == "PILGRIM'S PRIDE CORPORATION" and biggest.amount == 5_000_000
    assert biggest.payer_type == "organization"
    assert set(biggest.details) <= {"city", "state"}
    assert r.meta.citation == "FEC filing 1910509"


def test_past_presidency_pardon_page(fixture):
    r = DojClemency.parse(
        fixture("doj_clemency", "pardons-granted-president-joseph-biden-2021-2025.html")
    )
    assert r.meta.extra["president"] == "President Joseph Biden"
    # DOJ's statistics count 80 pardons on petition for this term.
    assert len(r.events) == 80 and all(e.kind == "pardoned" for e in r.events)
    family = [e for e in r.events if "nonviolent offenses" in e.details.get("offense", "")]
    assert {e.subject for e in family} == {
        "Francis W. Biden",
        "James B. Biden",
        "Sara Jones Biden",
        "John T. Owens",
        "Valerie Biden Owens",
    }
    hunter = next(e for e in r.events if e.subject == "Robert Hunter Biden")
    assert hunter.on == date(2024, 12, 1) and "Special Counsel" in hunter.details["offense"]
    # The January 6 committee row is one grant to a described group, not a person.
    (group,) = [e for e in r.events if not e.subject]
    assert group.title.startswith(
        "Pardon: The Members of Congress who served on the Select Committee"
    )
    assert "staff of the Select Committee" in group.title and group.details["group"]
    assert group.details["warrant_url"].startswith("https://www.justice.gov/")
    assert "#19-Jan-2025-pardon" in group.locator


def test_oldest_layout_one_long_table(fixture):
    r = DojClemency.parse(
        fixture("doj_clemency", "commutations-granted-president-william-j-clinton-1993-2001.html")
    )
    assert r.meta.extra["president"] == "President William J. Clinton"
    first = min(r.events, key=lambda e: e.on)
    assert first.subject == "Ernest Charles Krikava" and first.on == date(1994, 11, 23)
    assert first.kind == "commuted"
    assert (
        first.details["district"] == "Nebraska"
        and first.details["sentenced_on"] == "November 10, 1993"
    )
    assert first.details["terms"].startswith("Sentence of imprisonment to expire immediately")
    assert len(r.events) > 60
