"""USAspending.gov agency profiles: what each agency says it does, and what its money funds.

API, no key: https://api.usaspending.gov/docs/endpoints. US federal data, public domain.

  references/toptier_agencies/          every agency's budgetary resources this fiscal year
  agency/<code>/ + .../budget_function/ the agency's mission statement and website, and
                                        its gross outlays by budget function (one document)

Profiles are fetched for agencies above a budgetary-resources threshold, so the site can
say what the large spenders do in their own words. Missions are the agencies' own text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://api.usaspending.gov/api/v2"


class UsaSpendingAgencies(Adapter):
    name = "usaspending_agencies"
    jurisdiction = "US"
    description = "USAspending.gov agency profiles: missions, budgetary resources, functions"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        path = "references/toptier_agencies/"
        listing = self.http.get(f"{API}/{path}").json()
        item = {"kind": "toptier", "endpoint": path, "response": listing}
        yield self.json_raw("toptier_agencies", f"{API}/{path}", item)
        threshold = cfg.get("min_budget_authority", 1e9)
        for a in listing["results"]:
            if (a.get("budget_authority_amount") or 0) < threshold:
                continue
            code, fy = a["toptier_code"], int(a["active_fy"])
            # One document per agency: its own description, and its spending by function.
            profile = self.http.get(f"{API}/agency/{code}/").json()
            functions = self.http.get(
                f"{API}/agency/{code}/budget_function/", params={"fiscal_year": fy, "limit": 100}
            ).json()
            item = {
                "kind": "agency",
                "endpoint": f"agency/{code}/",
                "fiscal_year": fy,
                "profile": profile,
                "budget_function": functions,
            }
            yield self.json_raw(f"agency:{code}:FY{fy}", f"{API}/agency/{code}/", item)

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        if d["kind"] == "toptier":
            res = d["response"]
            rows = [
                {
                    "code": a["toptier_code"],
                    "name": a["agency_name"],
                    "abbreviation": a.get("abbreviation"),
                    "budget_authority": a.get("budget_authority_amount"),
                    "obligated": a.get("obligated_amount"),
                    "outlays": a.get("outlay_amount"),
                    "cj_url": a.get("congressional_justification_url"),
                    "slug": a.get("agency_slug"),
                }
                for a in res.get("results", [])
            ]
            fy = int(res["results"][0]["active_fy"]) if res.get("results") else None
            extra = {"kind": "toptier", "fiscal_year": fy, "rows": rows}
            title, url = f"Federal agencies' budgetary resources, FY{fy}", "agency"
        else:
            prof, fy = d["profile"], d["fiscal_year"]
            extra = {
                "kind": "agency",
                "fiscal_year": fy,
                "code": prof["toptier_code"],
                "name": prof["name"],
                "abbreviation": prof.get("abbreviation"),
                "mission": (prof.get("mission") or "").strip(),
                "website": prof.get("website"),
                "cj_url": prof.get("congressional_justification_url"),
                # Gross outlays by budget function, as the agency reports them to USAspending.
                "rows": [
                    {
                        "name": f["name"],
                        "gross_outlays": f.get("gross_outlay_amount"),
                        "obligated": f.get("obligated_amount"),
                    }
                    for f in d["budget_function"].get("results", [])
                ],
            }
            title = f"{prof['name']}: mission and spending by budget function, FY{fy}"
            url = "agency/" + re.sub(r"[^a-z0-9]+", "-", prof["name"].lower()).strip("-")
        published = date(extra["fiscal_year"], 9, 30) if extra.get("fiscal_year") else None
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="US",
                publisher="USAspending.gov (US Department of the Treasury)",
                doc_type="dataset",
                published_on=published,
                canonical_url=f"https://www.usaspending.gov/{url}",
                citation=f"USAspending.gov API, {d['endpoint']}",
                extra=extra,
            )
        )
