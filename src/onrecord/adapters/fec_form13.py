"""FEC Form 13: donations to presidential inaugural committees.

Inaugural committees must report every donation over $200 to the Federal Election
Commission (52 U.S.C. 30127). We archive the committee's raw electronic filing (.fec)
from FEC's public docquery server, which needs no key, and parse every line:
F13A = report summary, F132 = donation accepted, F133 = donation refunded.

Finding the current filings uses the FEC API (one request). It works with the public
DEMO_KEY; set FEC_API_KEY (free, api.data.gov) for higher limits.
Format reference: https://www.fec.gov/help-candidates-and-committees/filing-reports/
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime

from ..models import DocumentMeta, ParseResult, RawDocument, Transaction
from ..topics import Topic
from .base import Adapter

API = "https://api.open.fec.gov/v1"
RAW = "https://docquery.fec.gov/dcdev/posted/{file}.fec"
FS = "\x1c"  # .fec files separate fields with the ASCII file-separator character


def _date(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _payer(f: list[str]) -> tuple[str, str]:
    if f[5] == "IND":
        name = ", ".join(p for p in (f[7], " ".join(x for x in (f[8], f[9]) if x)) if p)
        suffix = " ".join(x for x in (f[11],) if x)
        return (f"{name} {suffix}".strip(), "individual")
    name = f[6]
    return (name, "unitemized" if name.upper().startswith("UNITEMIZED") else "organization")


class FecForm13(Adapter):
    name = "fec_form13"
    jurisdiction = "US"
    description = "FEC Form 13: donations to presidential inaugural committees"

    def current_filings(self, committee: str) -> list[dict]:
        """Latest amendment of each distinct Form 13 report the committee has filed."""
        key = os.environ.get("FEC_API_KEY") or "DEMO_KEY"
        resp = self.http.get(
            f"{API}/filings/",
            params={"committee_id": committee, "form_type": "F13", "per_page": 100, "api_key": key},
        )
        latest: dict[str, dict] = {}
        for f in resp.json().get("results", []):
            report = f.get("document_description") or f.get("report_type") or ""
            if report not in latest or f["file_number"] > latest[report]["file_number"]:
                latest[report] = f
        return list(latest.values())

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        for committee in cfg.get("committees", []):
            for filing in self.current_filings(committee):
                file_no = filing["file_number"]
                url = RAW.format(file=file_no)
                resp = self.http.get(url)
                yield RawDocument(
                    source=self.name,
                    source_id=f"{committee}:{file_no}",
                    url=url,
                    fetched_at=datetime.now(UTC),
                    content_type="text/plain",
                    body=resp.content,
                )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        lines = [ln.rstrip("\r").split(FS) for ln in raw.body.decode("latin-1").split("\n")]
        header = next(f for f in lines if f[0].startswith("F13A") or f[0].startswith("F13N"))
        committee_id, committee = header[1], header[2]
        file_no = raw.source_id.split(":")[-1]
        report_type, covers_from, covers_to = header[9], header[11], header[12]
        by = cls.extracted_by()

        txns: list[Transaction] = []
        for f in lines:
            if f[0] not in ("F132", "F133") or len(f) < 19:
                continue
            payer, payer_type = _payer(f)
            txns.append(
                Transaction(
                    kind="donation" if f[0] == "F132" else "refund",
                    payer=payer,
                    payer_type=payer_type,
                    payee=committee,
                    amount=float(f[18] or 0),
                    currency="USD",
                    on=_date(f[17]),
                    locator=f"FEC filing {file_no}, {f[0]} line {f[2]}",
                    extracted_by=by,
                    # City and state only: we don't republish donors' street addresses.
                    details={k: v for k, v in (("city", f[14]), ("state", f[15])) if v},
                )
            )

        received = header[21] if len(header) > 21 and header[21] else covers_to
        title = f"{committee}: Form 13 report {report_type} (FEC filing {file_no})"
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="US",
                publisher=committee,
                doc_type="fec_form13",
                published_on=_date(received),
                canonical_url=f"https://docquery.fec.gov/cgi-bin/forms/{committee_id}/{file_no}/",
                citation=f"FEC filing {file_no}",
                extra={
                    "committee_id": committee_id,
                    "report_type": report_type,
                    "coverage": [covers_from, covers_to],
                    "total_donations": float(header[13] or 0),
                    "total_refunds": float(header[14] or 0),
                    "net_donations": float(header[15] or 0),
                },
            ),
            transactions=txns,
        )
