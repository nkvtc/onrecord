"""US Federal Register: executive orders, proclamations, rules and notices.

API docs: https://www.federalregister.gov/developers/documentation/api/v1
No key required. Federal Register content is a US government work (public domain).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Event, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = [
    "document_number",
    "title",
    "type",
    "subtype",
    "abstract",
    "action",
    "dates",
    "publication_date",
    "signing_date",
    "effective_on",
    "executive_order_number",
    "proclamation_number",
    "citation",
    "html_url",
    "pdf_url",
    "raw_text_url",
    "agencies",
    "president",
]


class FederalRegister(Adapter):
    name = "federal_register"
    jurisdiction = "US"
    description = "US Federal Register: presidential documents, rules, notices"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        seen: set[str] = set()
        for q in cfg.get("queries", []):
            params: list[tuple[str, str]] = [
                ("per_page", "200"),
                ("order", "oldest"),
                ("conditions[publication_date][gte]", topic.since.isoformat()),
                ("conditions[term]", q["term"]) if "term" in q else None,
                *[("conditions[type][]", t) for t in q.get("types", [])],
                *[("conditions[agencies][]", a) for a in q.get("agencies", [])],
                *[("fields[]", f) for f in FIELDS],
            ]
            url: str | None = API
            query: list | None = [p for p in params if p]
            while url:
                resp = self.http.get(url, params=query)
                page = resp.json()
                for item in page.get("results", []):
                    num = item["document_number"]
                    if num in seen:
                        continue
                    seen.add(num)
                    yield self.json_raw(num, item.get("html_url") or str(resp.url), item)
                # next_page_url already carries every parameter.
                url, query = page.get("next_page_url"), None

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        num = d["document_number"]
        is_presidential = d.get("type") == "Presidential Document"
        doc_type = (d.get("subtype") if is_presidential else d.get("type")) or "document"
        doc_type = doc_type.lower().replace(" ", "_")
        agencies = [a.get("name") or a.get("raw_name") for a in d.get("agencies") or []]
        publisher = agencies[0] if agencies else "Federal Register"
        title = d["title"]
        cite = d.get("citation") or f"FR Doc. {num}"
        by = cls.extracted_by()

        number = d.get("executive_order_number") or d.get("proclamation_number")
        if number:
            label = "EO" if d.get("executive_order_number") else "Proc."
            title_with_no = f"{label} {number}: {title}"
        else:
            title_with_no = title

        events: list[Event] = []
        if is_presidential and d.get("signing_date"):
            president = (d.get("president") or {}).get("name", "President of the United States")
            events.append(
                Event(
                    kind="signed",
                    on=date.fromisoformat(d["signing_date"]),
                    jurisdiction="US",
                    actor=president,
                    title=title_with_no,
                    locator=f"{cite}; Federal Register API field signing_date",
                    extracted_by=by,
                )
            )
        events.append(
            Event(
                kind="published",
                on=date.fromisoformat(d["publication_date"]),
                jurisdiction="US",
                actor=publisher,
                title=title_with_no,
                locator=f"{cite}; Federal Register API field publication_date",
                extracted_by=by,
            )
        )
        if d.get("effective_on"):
            events.append(
                Event(
                    kind="effective",
                    on=date.fromisoformat(d["effective_on"]),
                    jurisdiction="US",
                    actor=publisher,
                    title=title_with_no,
                    locator=f"{cite}; Federal Register API field effective_on",
                    extracted_by=by,
                )
            )

        return ParseResult(
            meta=DocumentMeta(
                title=title_with_no,
                jurisdiction="US",
                publisher=publisher,
                doc_type=doc_type,
                published_on=date.fromisoformat(d["publication_date"]),
                canonical_url=d.get("html_url") or raw.url,
                citation=d.get("citation"),
                extra={
                    "document_number": num,
                    "abstract": d.get("abstract"),
                    "action": d.get("action"),
                    "dates": d.get("dates"),
                    "pdf_url": d.get("pdf_url"),
                    "raw_text_url": d.get("raw_text_url"),
                    "agencies": agencies,
                },
            ),
            events=events,
        )
