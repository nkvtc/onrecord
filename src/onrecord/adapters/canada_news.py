"""Government of Canada news releases and statements (canada.ca).

These are *claims*: what the government said, on the day it said it. A release saying
"Canada will impose countermeasures" is not the countermeasure; the legal instrument
is an Order in the Canada Gazette, which gets its own adapter.

API: https://api.io.canada.ca/io-server/gc/news/en/v2 (no key).
Content is published under the Open Government Licence – Canada.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import datetime

from ..models import Claim, DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://api.io.canada.ca/io-server/gc/news/en/v2"

DEPARTMENTS = {
    "departmentfinance": "Department of Finance Canada",
    "departmentofforeignaffairstradeanddevelopment": "Global Affairs Canada",
    "primeministersoffice": "Prime Minister's Office",
    "canadaborderservicesagency": "Canada Border Services Agency",
    "innovationsciencesandeconomicdevelopmentcanada": (
        "Innovation, Science and Economic Development Canada"
    ),
}


class CanadaNews(Adapter):
    name = "canada_news"
    jurisdiction = "CA"
    description = "Government of Canada news releases (statements, not legal instruments)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        # Word-start match: "tariff" catches "tariffs", but "u.s" can't match "focus.".
        keywords = [
            re.compile(r"(?<![\w.])" + re.escape(k.lower())) for k in cfg.get("keywords", [])
        ]
        for dept in cfg.get("departments", []):
            params = {
                "dept": dept,
                "sort": "publishedDate",
                "orderBy": "desc",
                "publishedDate>": topic.since.isoformat(),
                "pick": "1000",
                "format": "json",
            }
            resp = self.http.get(API, params=params)
            for entry in resp.json().get("feed", {}).get("entry", []):
                haystack = f"{entry.get('title', '')} {entry.get('teaser', '')}".lower()
                if keywords and not any(k.search(haystack) for k in keywords):
                    continue
                # Record which department feed it came from; the API item doesn't say.
                item = {**entry, "_department": dept}
                yield self.json_raw(entry["link"], entry["link"], item)

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        published = datetime.fromisoformat(d["publishedDate"])  # Ottawa local time
        dept = d.get("_department", "")
        speaker = DEPARTMENTS.get(dept, dept or "Government of Canada")
        teaser = (d.get("teaser") or "").strip()
        title = d["title"].replace("‎", "").strip()
        text = title if not teaser or teaser == title else f"{title} — {teaser}"
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="CA",
                publisher=speaker,
                doc_type="news_release",
                published_on=published.date(),
                canonical_url=d["link"],
                extra={"department": dept, "published_at": d["publishedDate"]},
            ),
            claims=[
                Claim(
                    speaker=speaker,
                    said_on=published.date(),
                    jurisdiction="CA",
                    text=text,
                    locator=f"{d['link']}; news API title and teaser",
                    extracted_by=cls.extracted_by(),
                )
            ],
        )
