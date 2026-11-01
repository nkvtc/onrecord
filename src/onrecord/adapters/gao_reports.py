"""US Government Accountability Office: newly published reports and testimonies.

RSS: https://www.gao.gov/rss/reports.xml (no key). The feed only carries the latest
items, so the archive grows by accumulation from the day collection started. Each item
is archived as its own XML fragment, exactly as served. US federal work, public domain.

GAO findings are recorded as *claims*: they are the auditor's statements, not actions.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from ..models import Claim, DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

FEED = "https://www.gao.gov/rss/reports.xml"


class GaoReports(Adapter):
    name = "gao_reports"
    jurisdiction = "US"
    description = "US Government Accountability Office reports and testimonies (RSS)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        resp = self.http.get(cfg.get("feed", FEED))
        for item in re.findall(rb"<item>.*?</item>", resp.content, re.S):
            guid = re.search(rb"<guid[^>]*>(.*?)</guid>", item, re.S)
            link = re.search(rb"<link>(.*?)</link>", item, re.S)
            source_id = (guid or link).group(1).decode().strip()
            yield RawDocument(
                source=self.name,
                source_id=source_id,
                url=link.group(1).decode().strip() if link else FEED,
                fetched_at=datetime.now(UTC),
                content_type="application/xml",
                body=item,
            )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        item = ET.fromstring(raw.body)
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or raw.url).strip()
        summary = re.sub(r"\s+", " ", item.findtext("description") or "").strip()
        published = parsedate_to_datetime(item.findtext("pubDate")).date()
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="US",
                publisher="US Government Accountability Office",
                doc_type="audit_report",
                published_on=published,
                canonical_url=link,
                citation=f"GAO {link.rsplit('/', 1)[-1].upper()}",
                extra={"abstract": summary},
            ),
            claims=[
                Claim(
                    speaker="US Government Accountability Office",
                    said_on=published,
                    jurisdiction="US",
                    text=f"{title} — {summary}" if summary else title,
                    locator=f"{link}; GAO reports RSS item",
                    extracted_by=cls.extracted_by(),
                )
            ],
        )
