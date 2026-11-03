from onrecord.export import build_records, record_key


def _item(title, date="2025-01-19", source="doj_clemency", summary=None, n=0):
    return {
        "id": f"{source}:page#{n}",
        "source": source,
        "date": date,
        "doc_type": "pardoned",
        "title": title,
        "publisher": "US Department of Justice, Office of the Pardon Attorney",
        "citation": None,
        "url": "https://www.justice.gov/pardon/media/1/dl?inline",
        "summary": summary,
        "events": [
            {
                "kind": "pardoned",
                "on": date,
                "actor": "President Joseph Biden",
                "locator": 'https://www.justice.gov/pardon/page#19-Jan; section "Jan 19"',
            }
        ],
    }


def test_record_key_ignores_position_on_the_page():
    # The DOJ page adds entries in place, shifting item ids; a shared link must still
    # point at the same grant.
    assert record_key(_item("Pardon: Anthony S. Fauci", n=3)) == record_key(
        _item("Pardon: Anthony S. Fauci", n=7)
    )
    fauci, milley = _item("Pardon: Anthony S. Fauci"), _item("Pardon: Mark A. Milley")
    assert record_key(fauci) != record_key(milley)


def test_records_merge_topics_and_keep_the_source_page():
    a = _item("Pardon: Anthony S. Fauci", summary="offense: For any offenses ...")
    rows = build_records({"accountability": [a], "history": [dict(a, id="other")]})
    (r,) = rows
    assert r["topics"] == ["accountability", "history"]
    assert r["who"] == "President Joseph Biden"
    assert r["page"] == "https://www.justice.gov/pardon/page#19-Jan"
    assert r["summary"].startswith("offense:")
