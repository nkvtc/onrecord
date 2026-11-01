"""USAspending.gov: where federal award money goes, by place and by recipient.

API, no key: https://api.usaspending.gov/docs/endpoints. US federal data, public domain.

Each request is archived with its response, and parsed into table rows kept on the
document (meta.extra["rows"]) for the site's map and charts. They are "rows" rather
than time series because they are snapshots of one fiscal year by one breakdown.

What the numbers are: obligations on federal awards (contracts, grants, loans, direct
payments) as agencies report them to USAspending, by place of performance. They do not
include federal salaries. "Place of performance" can be where a contractor or claims
processor is located rather than where the benefit is used, which is why the site shows
the agency breakdown next to the map.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://api.usaspending.gov/api/v2"
STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY",
]  # fmt: skip


def fiscal_year(fy: int) -> dict:
    return {"start_date": f"{fy - 1}-10-01", "end_date": f"{fy}-09-30"}


class UsaSpending(Adapter):
    name = "usaspending"
    jurisdiction = "US"
    description = "USAspending.gov: federal award spending by state, county, agency, recipient"

    def _post(self, kind: str, key: str, path: str, body: dict) -> RawDocument:
        resp = self.http.post(f"{API}/{path}", json=body)
        item = {"kind": kind, "endpoint": path, "request": body, "response": resp.json()}
        return self.json_raw(key, f"{API}/{path}", item)

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        for fy in cfg.get("state_years", []):
            body = {
                "scope": "place_of_performance",
                "geo_layer": "state",
                "filters": {"time_period": [fiscal_year(fy)]},
            }
            yield self._post(
                "geo_state", f"geo:state:FY{fy}", "search/spending_by_geography/", body
            )
        for fy in cfg.get("county_years", []):
            body = {
                "scope": "place_of_performance",
                "geo_layer": "county",
                "filters": {"time_period": [fiscal_year(fy)]},
            }
            yield self._post(
                "geo_county", f"geo:county:FY{fy}", "search/spending_by_geography/", body
            )
        if fy := cfg.get("detail_year"):
            for state in STATES:
                body = {
                    "filters": {
                        "time_period": [fiscal_year(fy)],
                        "place_of_performance_locations": [{"country": "USA", "state": state}],
                    },
                    "limit": 10,
                }
                yield self._post(
                    "agencies_by_state",
                    f"agencies:{state}:FY{fy}",
                    "search/spending_by_category/awarding_agency/",
                    body,
                )
            body = {
                "filters": {
                    "time_period": [fiscal_year(fy)],
                    "award_type_codes": ["A", "B", "C", "D"],
                },
                "limit": 25,
            }
            yield self._post(
                "top_contractors",
                f"contractors:FY{fy}",
                "search/spending_by_category/recipient/",
                body,
            )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        kind, req, res = d["kind"], d["request"], d["response"]
        period = req["filters"]["time_period"][0]
        fy = int(period["end_date"][:4])
        results = res.get("results", [])
        if kind.startswith("geo_"):
            rows = [
                {
                    "code": r.get("shape_code"),
                    "name": r.get("display_name"),
                    "amount": r.get("aggregated_amount"),
                    "population": r.get("population"),
                    "per_capita": r.get("per_capita"),
                }
                for r in results
            ]
            layer = "state" if kind == "geo_state" else "county"
            title = f"Federal award spending by {layer}, FY{fy}"
        elif kind == "agencies_by_state":
            state = req["filters"]["place_of_performance_locations"][0]["state"]
            rows = [{"name": r.get("name"), "amount": r.get("amount")} for r in results]
            title = f"Federal award spending in {state} by awarding agency, FY{fy}"
        else:
            # Names as reported; the same company can appear under several recipient IDs.
            rows = [
                {
                    "name": r.get("name"),
                    "amount": r.get("amount"),
                    "recipient_id": r.get("recipient_id"),
                }
                for r in results
            ]
            title = f"Largest federal contract recipients, FY{fy}"
        extra = {"kind": kind, "fiscal_year": fy, "rows": rows}
        if kind == "agencies_by_state":
            extra["state"] = req["filters"]["place_of_performance_locations"][0]["state"]
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="US",
                publisher="USAspending.gov (US Department of the Treasury)",
                doc_type="dataset",
                published_on=date.fromisoformat(period["end_date"]),
                canonical_url="https://www.usaspending.gov/search",
                citation=f"USAspending.gov API, {d['endpoint']}, FY{fy}",
                extra=extra,
            )
        )
