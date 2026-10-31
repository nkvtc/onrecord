"""Historical comparison sources and the panels computed from them."""

import json
from dataclasses import replace
from datetime import date

from onrecord.adapters.doj_clemency_stats import DojClemencyStats
from onrecord.adapters.fec_inaugural_totals import FecInauguralTotals
from onrecord.adapters.federal_register import FederalRegister
from onrecord.panels import clemency_by_president, eo_pace, inaugural_totals
from onrecord.store import Store


def test_clemency_stats_all_presidents(fixture):
    r = DojClemencyStats.parse(fixture("doj_clemency_stats", "clemency-statistics.html"))
    by = {p["president"]: p for p in r.meta.extra["presidents"]}
    assert len(by) == 22
    assert (by["Barack H. Obama"]["pardons"], by["Barack H. Obama"]["commutations"]) == (212, 1715)
    assert (by["Joseph R. Biden"]["pardons"], by["Joseph R. Biden"]["commutations"]) == (80, 4165)
    # Older tables label only the "Granted" columns; they must still parse, not read as 0.
    assert (by["John F. Kennedy"]["pardons"], by["John F. Kennedy"]["commutations"]) == (472, 100)
    # Tables without a total row are summed from their fiscal years.
    assert by["Calvin Coolidge"]["total_row"] == "Sum of fiscal years"
    assert by["Calvin Coolidge"]["pardons"] == 773
    assert all(p["pardons"] > 0 for p in by.values())


def test_inaugural_total_from_paper_filing(fixture):
    r = FecInauguralTotals.parse(fixture("fec_inaugural_totals", "C00409011.json"))
    (obs,) = r.observations
    assert obs.value == 42_790_021.0  # the supplement, not the earlier 90-day report
    assert obs.period == date(2005, 1, 20)
    # Paper filings have no file number: cite the scanned image instead of "None".
    assert r.meta.citation == "FEC image 25038844606"
    assert r.meta.canonical_url.endswith("25038844606.pdf")
    assert "api_key" not in r.meta.canonical_url


def test_eo_pace_counts_distinct_order_numbers(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("federal_register", "2025-02406.json")  # EO 14193, signed 2025-02-01
    store.ingest(raw, FederalRegister.parse(raw), topic="h")
    # A correction is a separate Federal Register document carrying the same order number.
    corr = json.loads(raw.body)
    corr["document_number"] = "C1-2025-02406"
    corr["title"] = "Correction"
    raw2 = replace(raw, source_id="C1-2025-02406", body=json.dumps(corr).encode())
    store.ingest(raw2, FederalRegister.parse(raw2), topic="h")

    p = eo_pace(store, today=date(2025, 3, 1))
    current = next(t for t in p["terms"] if t["current"])
    assert current["total"] == 1  # not 2
    assert current["points"] == [[12, 1]]  # day 12 of the term
    assert p["day_now"] == 40
    assert all(t["by_same_day"] == 0 for t in p["terms"] if not t["current"])
    assert "distinct executive order numbers" in p["rule"]


def test_clemency_panel_reports_current_term_separately(tmp_path, fixture):
    from onrecord.adapters.doj_clemency import DojClemency

    store = Store(tmp_path)
    for adapter, src, name in (
        (DojClemencyStats, "doj_clemency_stats", "clemency-statistics.html"),
        (DojClemency, "doj_clemency", "clemency-grants-president-donald-j-trump-2025-present.html"),
    ):
        raw = fixture(src, name)
        store.ingest(raw, adapter.parse(raw), topic="h")
    p = clemency_by_president(store, date(2026, 10, 30))
    assert len(p["presidents"]) == 22
    assert p["current_term"] == {
        "named_grants": 171,
        "grants_by_proclamation": 2,
        "url": "https://www.justice.gov/pardon/clemency-grants-president-donald-j-trump-2025-present",
    }


def test_inaugural_panel(tmp_path, fixture):
    store = Store(tmp_path)
    raw = fixture("fec_inaugural_totals", "C00409011.json")
    store.ingest(raw, FecInauguralTotals.parse(raw), topic="h")
    (row,) = inaugural_totals(store, date(2026, 10, 30))["rows"]
    assert row["label"] == "Bush 2005" and row["total"] == 42_790_021.0


def test_negative_fec_file_numbers_cite_the_scan():
    from onrecord.adapters.fec_inaugural_totals import filing_ref

    f = {
        "file_number": -9626062,
        "beginning_image_number": "201909170300294801",
        "pdf_url": "https://docquery.fec.gov/pdf/801/201909170300294801/201909170300294801.pdf",
    }
    assert filing_ref("C00629584", f) == ("FEC image 201909170300294801", f["pdf_url"])
