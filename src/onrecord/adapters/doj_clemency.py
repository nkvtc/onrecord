"""US Department of Justice, Office of the Pardon Attorney: clemency grants.

The Pardon Attorney publishes one page per presidency listing every pardon and
commutation, grouped under dated headings ("January 22, 2025 - 2 Pardons"), with name
(linked to the signed warrant), district, sentence and offense. Mass grants made by
proclamation (e.g. January 6 defendants) appear as a heading plus a link, with no names.

We archive the whole page on every pull. Because it's edited in place (entries are
added and marked "(Amended)"), each change becomes a new archived version.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urljoin

from ..models import DocumentMeta, Event, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

HEADING_RE = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})\s*(?:[-–—]\s*(.*))?$")


def _text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>|</p>", "; ", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    text = re.sub(r"\s+", " ", text.replace(" ", " ")).strip(" ;")
    return re.sub(r"\s*;\s*(;\s*)*", "; ", text)


def _kind(section: str) -> str:
    s = section.lower()
    if "pardon" in s and "commutation" in s:
        return "clemency"  # the table doesn't say which applies to each person
    return "commuted" if "commutation" in s else "pardoned"


LABELS = {
    "pardoned": "Pardon",
    "commuted": "Commutation",
    "clemency": "Pardon or commutation",
}


class DojClemency(Adapter):
    name = "doj_clemency"
    jurisdiction = "US"
    description = "DOJ Office of the Pardon Attorney: pardons and commutations"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        for url in cfg.get("pages", []):
            resp = self.http.get(url)
            yield RawDocument(
                source=self.name,
                source_id=url,
                url=url,
                fetched_at=datetime.now(UTC),
                content_type="text/html",
                body=resp.content,
            )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        page = raw.body.decode("utf-8", errors="replace")
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        page_title = _text(title_m.group(1)) if title_m else "Clemency grants"
        president = "President Donald J. Trump" if "Trump" in page_title else "The President"
        body_start = page.find("field_body")
        body = page[body_start:] if body_start >= 0 else page
        by = cls.extracted_by()

        events: list[Event] = []
        # Each <h3> opens a section that runs until the next <h3>.
        parts = re.split(r"<h3[^>]*>", body)[1:]
        for part in parts:
            head_html, _, rest = part.partition("</h3>")
            anchor = re.search(r'id="([^"]+)"', head_html)
            heading = _text(head_html)
            m = HEADING_RE.match(heading)
            if not m:
                continue
            on = datetime.strptime(m.group(1), "%B %d, %Y").date()
            section_text = m.group(2) or ""
            locator = f'{raw.url}{"#" + anchor.group(1) if anchor else ""}; section "{heading}"'
            table = re.search(r"<table.*?</table>", rest, re.S)
            if not table:
                # A grant by proclamation: a heading with a link, no named individuals.
                link = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', rest, re.S)
                if not link:
                    continue
                events.append(
                    Event(
                        kind="clemency",
                        on=on,
                        jurisdiction="US",
                        actor=president,
                        title=_text(link.group(2)),
                        locator=locator,
                        extracted_by=by,
                        details={
                            "document_url": urljoin(raw.url, html.unescape(link.group(1))),
                            "note": (
                                "Grant by proclamation; individuals are not itemized on this page."
                            ),
                        },
                    )
                )
                continue
            kind = _kind(section_text)
            tbody = re.search(r"<tbody>(.*?)</tbody>", table.group(0), re.S)
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1) if tbody else "", re.S):
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                if len(cells) < 4:
                    continue
                name = _text(cells[0])
                if not name:
                    continue
                warrant = re.search(r'href="([^"]+)"', cells[0])
                details = {
                    "district": _text(cells[1]),
                    "sentence": _text(cells[2]),
                    "offense": _text(cells[3]),
                    "section": heading,
                }
                if warrant:
                    details["warrant_url"] = urljoin(raw.url, html.unescape(warrant.group(1)))
                events.append(
                    Event(
                        kind=kind,
                        on=on,
                        jurisdiction="US",
                        actor=president,
                        title=f"{LABELS[kind]}: {name}",
                        locator=locator,
                        extracted_by=by,
                        subject=name,
                        details=details,
                    )
                )

        return ParseResult(
            meta=DocumentMeta(
                title=page_title,
                jurisdiction="US",
                publisher="US Department of Justice, Office of the Pardon Attorney",
                doc_type="clemency_list",
                published_on=max((e.on for e in events), default=None),
                canonical_url=raw.url,
                extra={"itemize_events": True, "grants_listed": len(events)},
            ),
            events=events,
        )
