"""Bills that split Congress: House roll call headers, bill status, the contested rule."""

from datetime import date

from onrecord.adapters.congress_bills import CongressBills, bill_key
from onrecord.panels import contested_bills, spending_laws
from onrecord.store import Store


def test_bill_key():
    assert bill_key("H R 1") == ("hr", 1)
    assert bill_key("S J RES 13") == ("sjres", 13)
    assert bill_key("H RES 780") is None  # a House rule, not a bill
    assert bill_key("") is None


def test_roll_call_header_from_partial_file(fixture):
    # Only the first 8KB of the roll call file is archived; the header must still parse.
    x = CongressBills.parse(fixture("congress_bills", "house_2025_137.xml")).meta.extra
    assert (x["bill"], x["question"], x["yea"], x["nay"]) == ("sjres13", "On Passage", 220, 207)
    rep = next(p for p in x["rows"] if p["party"] == "Republican")
    assert (rep["yea"], rep["nay"]) == (219, 0)


def test_full_roll_call_has_every_member(fixture):
    x = CongressBills.parse(fixture("congress_bills", "house_2025_137_full.xml")).meta.extra
    assert x["majority"] == "R"
    votes = [m["vote"] for m in x["members"]]
    assert votes.count("Yea") == 220 and votes.count("Nay") == 207
    assert all(m["id"] and m["party"] and m["state"] for m in x["members"])


def test_bill_status(fixture):
    r = CongressBills.parse(fixture("congress_bills", "bill_119sjres13.xml"))
    x = r.meta.extra
    assert x["law"] == "Public Law 119-19" and x["sponsor"].startswith("Sen. Kennedy")
    assert [(f["chamber"], f["yea"], f["nay"]) for f in x["rows"]] == [
        ("Senate", 52, 47),
        ("House", 220, 207),
    ]
    assert x["summary"]["text"].startswith("This joint resolution nullifies")
    assert sorted(e.kind for e in r.events) == ["adopted", "passed", "passed", "proposed"]


def test_contested_rule(tmp_path, fixture):
    store = Store(tmp_path)
    for name in ("house_2025_137_full.xml", "bill_119sjres13.xml"):
        raw = fixture("congress_bills", name)
        store.ingest(raw, CongressBills.parse(raw), topic="c")
    p = contested_bills(store, date(2026, 11, 2))
    (b,) = p["bills"]
    assert b["contested"] and b["party_line"] and b["status"] == "Became law"
    house = next(v for v in b["votes"] if v["chamber"] == "House")
    assert house["url"] == "https://clerk.house.gov/Votes/2025137"
    assert "40%" in p["rule"]
    # One vote code per member, aligned with the member list.
    assert len(house["codes"]) == len(p["members"]) and house["codes"].count("Y") == 220

    s = spending_laws(store, date(2026, 11, 2))
    assert s["bills"] == []  # a rule disapproval is not a spending bill
