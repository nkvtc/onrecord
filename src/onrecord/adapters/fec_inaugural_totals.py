"""FEC: total donations reported by each presidential inaugural committee.

Uses the FEC API's list of Form 13 filings for each committee (one request each).
Every filing reports a cumulative total. Committees file a 90-day report (90D) and
later a supplement (90S) covering donations after the deadline, and amend both, so
the figure shown is the total from the most recently received supplement, or the
most recent 90-day report when there is no supplement.

Works with the public DEMO_KEY; set FEC_API_KEY (free) for higher limits.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://api.open.fec.gov/v1/filings/"


def filing_ref(committee_id: str, f: dict) -> tuple[str, str]:
    """(citation, url) for one filing. Older reports were filed on paper: no file number,
    only scanned images (FEC marks some with negative numbers), so they're cited by image
    number and linked to the scan."""
    if (f.get("file_number") or 0) > 0:  # FEC gives paper amendments negative numbers
        n = f["file_number"]
        return f"FEC filing {n}", f"https://docquery.fec.gov/cgi-bin/forms/{committee_id}/{n}/"
    image = f.get("beginning_image_number")
    url = f.get("pdf_url") or f"https://www.fec.gov/data/committee/{committee_id}/"
    return (f"FEC image {image}" if image else "FEC paper filing"), url


def pick_filing(filings: list[dict]) -> dict | None:
    """The filing whose total best answers "how much was raised in all"."""
    for report in ("90S", "90D"):
        candidates = [
            f for f in filings if f.get("report_type") == report and f.get("total_receipts")
        ]
        if candidates:
            return max(
                candidates,
                key=lambda f: (
                    f.get("receipt_date") or "",
                    f.get("file_number") or 0,
                    f.get("beginning_image_number") or "",
                ),
            )
    return None


class FecInauguralTotals(Adapter):
    name = "fec_inaugural_totals"
    jurisdiction = "US"
    description = "FEC: total donations reported by presidential inaugural committees"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        key = os.environ.get("FEC_API_KEY") or "DEMO_KEY"
        for c in cfg.get("committees", []):
            resp = self.http.get(
                API,
                params={
                    "committee_id": c["id"],
                    "form_type": "F13",
                    "per_page": 100,
                    "api_key": key,
                },
            )
            filings = resp.json().get("results", [])
            # Keep the committee entry from the topic file with the response, and never
            # store the API key: the archived URL is the key-free form.
            url = f"{API}?committee_id={c['id']}&form_type=F13"
            item = {"committee": c, "filings": filings}
            yield self.json_raw(c["id"], url, item)

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        c = d["committee"]
        chosen = pick_filing(d["filings"])
        inauguration = date.fromisoformat(c["inauguration"])
        observations = []
        extra = {"committee_id": c["id"], "label": c["label"], "inauguration": c["inauguration"]}
        if chosen:
            name = chosen.get("committee_name") or c["id"]
            citation, url = filing_ref(c["id"], chosen)
            extra.update(
                {
                    "committee_name": name,
                    "total_receipts": chosen["total_receipts"],
                    "file_number": chosen.get("file_number"),
                    "citation": citation,
                    "filing_url": url,
                    "report": chosen.get("document_description") or chosen.get("report_type"),
                    "receipt_date": (chosen.get("receipt_date") or "")[:10],
                }
            )
            observations.append(
                Observation(
                    series_id="fec:inaugural_total_receipts",
                    series_label="Total donations reported by presidential inaugural committees",
                    period=inauguration,
                    value=float(chosen["total_receipts"]),
                    unit="USD",
                    released_at=extra["receipt_date"] or None,
                )
            )
        return ParseResult(
            meta=DocumentMeta(
                title=f"{c['label']}: inaugural committee Form 13 filings",
                jurisdiction="US",
                publisher=extra.get("committee_name", c["id"]),
                doc_type="fec_filing_list",
                published_on=date.fromisoformat(extra["receipt_date"]) if chosen else None,
                canonical_url=extra.get("filing_url")
                or f"https://www.fec.gov/data/committee/{c['id']}/",
                citation=extra.get("citation"),
                extra=extra,
            ),
            observations=observations,
        )
