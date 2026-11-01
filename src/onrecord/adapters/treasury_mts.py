"""US Treasury Monthly Treasury Statement (MTS), Table 9: receipts by source.

Fiscal Data API, no key: https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/
Table 9 reports *net* receipts by month. For customs duties, a negative month means
refunds paid out exceeded duties collected that month. US federal data, public domain.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_9"
)
FIELDS = "record_date,classification_desc,current_month_rcpt_outly_amt,current_fytd_rcpt_outly_amt"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


class TreasuryMts(Adapter):
    name = "treasury_mts"
    jurisdiction = "US"
    description = "US Treasury Monthly Treasury Statement, Table 9: receipts by source"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        for s in cfg.get("series", []):
            params = {
                "filter": f"classification_desc:eq:{s['classification']}",
                "sort": "record_date",
                "fields": FIELDS,
                "page[size]": "1000",
            }
            resp = self.http.get(API, params=params)
            item = {"series": s, "response": resp.json()}
            yield self.json_raw(f"mts9:{_slug(s['classification'])}", str(resp.url), item)

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        s = d["series"]
        rows = d["response"].get("data", [])
        series_id = f"treasury:mts9:{_slug(s['classification'])}"
        label = f"{s['label']} (Monthly Treasury Statement, Table 9, net receipts)"
        observations = []
        for r in rows:
            amount = r.get("current_month_rcpt_outly_amt")
            if amount in (None, "", "null"):
                continue
            end = date.fromisoformat(r["record_date"])
            observations.append(
                Observation(
                    series_id=series_id,
                    series_label=label,
                    period=date(end.year, end.month, 1),
                    value=round(float(amount) / 1e6, 3),
                    unit="USD millions",
                    released_at=None,
                )
            )
        last = rows[-1]["record_date"] if rows else None
        return ParseResult(
            meta=DocumentMeta(
                title=label,
                jurisdiction="US",
                publisher="US Department of the Treasury, Bureau of the Fiscal Service",
                doc_type="statistical_series",
                published_on=date.fromisoformat(last) if last else None,
                canonical_url="https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/receipts-of-the-u-s-government",
                citation=f'Monthly Treasury Statement, Table 9, "{s["classification"]}"',
                extra={"classification": s["classification"]},
            ),
            observations=observations,
        )
