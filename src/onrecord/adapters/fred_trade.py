"""US-side trade figures: US Census Bureau goods trade by country, via FRED.

The Census Bureau's own API now requires a key. The Federal Reserve Bank of St. Louis
republishes the same Census series (FT-900 country data) on FRED, downloadable as CSV
with no key. Labels say "via FRED" so nobody mistakes the republisher for the source.

Series are listed in the topic file with their FRED id and a label. Census country
series are monthly, millions of US dollars, not seasonally adjusted.
CSV endpoint: https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredTrade(Adapter):
    name = "fred_trade"
    jurisdiction = "US"
    description = "US Census Bureau goods trade by partner country (republished on FRED)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        start = date(topic.since.year - 1, 1, 1).isoformat()
        for s in cfg.get("series", []):
            resp = self.http.get(CSV_URL, params={"id": s["id"], "cosd": start})
            # Wrap the CSV with the label from the topic file, so parse() stays pure.
            item = {"series": s, "csv": resp.text, "url": str(resp.url)}
            yield RawDocument(
                source=self.name,
                source_id=s["id"],
                url=str(resp.url),
                fetched_at=datetime.now(UTC),
                content_type="application/json",
                body=json.dumps(item, sort_keys=True, indent=1).encode(),
            )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        s = d["series"]
        label = f"{s['label']} (US Census Bureau via FRED, not seasonally adjusted)"
        rows = list(csv.reader(io.StringIO(d["csv"])))
        observations = []
        for row in rows[1:]:
            if len(row) < 2 or row[1] in ("", "."):
                continue  # FRED marks missing values with "."
            observations.append(
                Observation(
                    series_id=f"fred:{s['id']}",
                    series_label=label,
                    period=date.fromisoformat(row[0]),
                    value=float(row[1]),
                    unit="USD millions",
                    released_at=None,
                )
            )
        last = observations[-1].period if observations else None
        return ParseResult(
            meta=DocumentMeta(
                title=label,
                jurisdiction="US",
                publisher="US Census Bureau (republished by the Federal Reserve Bank of St. Louis)",
                doc_type="statistical_series",
                published_on=last,
                canonical_url=f"https://fred.stlouisfed.org/series/{s['id']}",
                citation=f"U.S. Census Bureau, retrieved from FRED, series {s['id']}",
                extra={"fred_id": s["id"]},
            ),
            observations=observations,
        )
