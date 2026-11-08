"""US Department of Justice, Office of the Pardon Attorney: clemency grants.

The Pardon Attorney publishes one page per presidency listing every pardon and
commutation, grouped under dated headings ("January 22, 2025 - 2 Pardons"), with name
(linked to the signed warrant), district, sentence and offense. Mass grants made by
proclamation (e.g. January 6 defendants) appear as a heading plus a link, with no names.

Past presidencies have separate pardon and commutation pages in two older layouts: a
table per date (as above, sometimes with several names in one cell), or one long table
where each person is a bold name followed by "Offense:", "District/Date:", "Sentence:"
and "Terms of grant:" rows, with the date headings inside the table.

We archive the whole page on every pull. Because it's edited in place (entries are
added and marked "(Amended)"), each change becomes a new archived version.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime
from urllib.parse import urljoin

from ..models import DocumentMeta, Event, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

HEADING_RE = re.compile(r"^([A-Za-z]+\.? \d{1,2}, \d{4})\s*(?:[-–—]\s*(.*))?$")
# Headings, table rows and links, in page order.
TOKEN_RE = re.compile(
    r"<h[2-4][^>]*>(?P<head>.*?)</h[2-4]>"
    r"|<tr\b(?:(?!<h[2-4]).)*?</tr>"  # a row never swallows a date heading
    r'|<a\b[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<label>.*?)</a>',
    re.S,
)
PRESIDENT_RE = re.compile(r"President ([A-Z][\w.]*(?: [A-Z][\w.]*)*)")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
FIELDS = {"offense": "offense", "sentence": "sentence", "terms of grant": "terms"}
NEXT_IS_OFFENSE = re.compile(r"\s*<tr\b(?:(?!</tr>).){0,400}?Offense:", re.S)


def _text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>|</p>", "; ", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    text = re.sub(r"\s+", " ", text.replace(" ", " ")).strip(" ;")
    return re.sub(r"\s*;\s*(;\s*)*", "; ", text)


def _kind(section: str) -> str:
    s = section.lower()
    if "pardon" in s and "commutation" in s:
        return "clemency"  # the table doesn't say which applies to each person
    return "commuted" if "commutation" in s else "pardoned"


def _date(s: str) -> date:
    m = re.match(r"([A-Za-z]+)\.? (\d{1,2}), (\d{4})", s)
    return date(int(m.group(3)), MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2)))


def _column(head: str) -> str:
    """Header text varies by page ("NAME and WARRANT", "SENTENCED")."""
    for name in ("NAME", "DISTRICT", "SENTENCED", "OFFENSE", "DESCRIPTION"):
        if head.startswith(name[:7]):
            return name
    return head


def _names(cell: str) -> list[str]:
    """One cell can name several people: Biden's family pardons are a single row."""
    parts = [p for p in (_text(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", cell, re.S)) if p]
    if len(parts) > 1 and all(len(p) < 60 for p in parts):
        return parts
    return [_text(cell)]


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
        try:
            page = raw.body.decode("utf-8")
        except UnicodeDecodeError:  # some older pages are Windows-1252
            page = raw.body.decode("cp1252", errors="replace")
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        page_title = _text(title_m.group(1)) if title_m else "Clemency grants"
        who = PRESIDENT_RE.search(page_title)
        president = f"President {who.group(1)}" if who else "The President"
        # "Pardons Granted by ..." pages list one kind; "Clemency Grants" pages say per date.
        page_kind = "clemency" if "clemency" in page_title.lower() else _kind(page_title)
        body_start = page.find("field_body")
        body = page[body_start:] if body_start >= 0 else page
        by = cls.extracted_by()

        events: list[Event] = []
        section: dict | None = None
        columns: list[str] | None = None
        person: dict | None = None

        def close_person():
            nonlocal person
            if person and section:
                events.extend(_grants(person, section, president, by))
            person = None

        def close_section():
            close_person()
            if section and not section["rows"] and section["link"]:
                # A grant by proclamation: a heading with a link, no named individuals.
                url, label = section["link"]
                events.append(
                    Event(
                        kind="clemency",
                        on=section["on"],
                        jurisdiction="US",
                        actor=president,
                        title=label,
                        locator=section["locator"],
                        extracted_by=by,
                        details={
                            "document_url": url,
                            "note": (
                                "Grant by proclamation; individuals are not itemized on this page."
                            ),
                        },
                    )
                )

        for m in TOKEN_RE.finditer(body):
            tok = m.group(0)
            if m.group("head") is not None:
                heading = _text(m.group("head"))
                d = HEADING_RE.match(heading)
                if not d:
                    continue
                close_section()
                anchor = re.search(r'id="([^"]+)"', tok) or re.search(
                    r'id="([^"]+)"[^<]*</a>\s*(?:</p>)?\s*$',
                    body[max(0, m.start() - 200) : m.start()],
                )
                rest = d.group(2) or ""
                has_kind = re.search(r"pardon|commutation", rest, re.I)
                section = {
                    "on": _date(d.group(1)),
                    "heading": heading,
                    "kind": _kind(rest) if has_kind else page_kind,
                    "locator": f"{raw.url}{'#' + anchor.group(1) if anchor else ''}; "
                    f'section "{heading}"',
                    "rows": 0,
                    "link": None,
                    "warrant": None,
                }
                columns = None
                continue
            if section is None:
                continue
            if m.group("href") is not None:
                label = _text(m.group("label"))
                href = urljoin(raw.url, html.unescape(m.group("href")))
                if "warrant" in label.lower():
                    section["warrant"] = section["warrant"] or href
                elif label and not section["link"]:
                    section["link"] = (href, label)
                continue

            # A table row.
            heads = [_text(c).upper() for c in re.findall(r"<th[^>]*>(.*?)</th>", tok, re.S)]
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tok, re.S)
            texts = [_text(c) for c in cells]
            if heads or (texts and texts[0].upper() in ("NAME", "DESCRIPTION")):
                columns = [_column(h) for h in (heads or [t.upper() for t in texts])]
                continue
            if (
                len(cells) == 2
                and not texts[0]
                and texts[1]
                and (
                    re.search(r"<(strong|b)\b", cells[1])
                    # Some names on the Obama page aren't bold (Chelsea Manning's, for one);
                    # a name row is still recognisable by the "Offense:" row right after it.
                    or NEXT_IS_OFFENSE.match(body, m.end())
                )
            ):
                # Older layout: a bold name, then "Offense:", "Sentence:" ... rows.
                close_person()
                person = {"names": [texts[1]]}
                section["rows"] += 1
                continue
            if len(cells) == 2 and texts[0].endswith(":"):
                if person:
                    key = texts[0].rstrip(":").lower()
                    if key.startswith("district"):
                        district, _, sentenced = texts[1].partition(";")
                        person["district"] = district.strip()
                        if sentenced.strip():
                            person["sentenced_on"] = sentenced.strip()
                    elif key in FIELDS:
                        person[FIELDS[key]] = texts[1]
                continue
            if not any(texts):
                continue
            cols = columns or (
                ["NAME", "DISTRICT", "SENTENCED", "OFFENSE"] if len(cells) >= 4 else None
            )
            if not cols:
                continue
            close_person()
            row = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(cols)}
            warrant = re.search(r'href="([^"]+)"', tok)
            described = "DESCRIPTION" in row
            person = {
                "names": [_text(row["DESCRIPTION"])] if described else _names(row.get("NAME", "")),
                "group": described,
                "district": _text(row.get("DISTRICT", "")),
                "sentence": _text(row.get("SENTENCED", "")),
                "offense": _text(row.get("OFFENSE", "")),
                "warrant": urljoin(raw.url, html.unescape(warrant.group(1))) if warrant else None,
            }
            section["rows"] += 1
            close_person()
        close_section()

        return ParseResult(
            meta=DocumentMeta(
                title=page_title,
                jurisdiction="US",
                publisher="US Department of Justice, Office of the Pardon Attorney",
                doc_type="clemency_list",
                published_on=max((e.on for e in events), default=None),
                canonical_url=raw.url,
                extra={
                    "itemize_events": True,
                    "grants_listed": len(events),
                    "president": president,
                },
            ),
            events=events,
        )


def _grants(person: dict, section: dict, president: str, by) -> Iterator[Event]:
    kind = section["kind"]
    details = {
        k: person[k]
        for k in ("district", "sentence", "offense", "terms", "sentenced_on")
        if person.get(k)
    }
    details["section"] = section["heading"]
    warrant = person.get("warrant") or section["warrant"]
    if warrant:
        details["warrant_url"] = warrant
    for name in person["names"]:
        # Skip blanks and footnotes ("* This clemency grant supersedes ...").
        if not name or name.upper() == "N/A" or re.match(r"[*\d]", name):
            continue
        # A row describing a group ("The Members of Congress who served on ...",
        # "Commutation granted to 1,499 individuals") is one grant, not a named person.
        group = person.get("group") or name.lower().startswith("the ") or len(name) > 150
        yield Event(
            kind=kind,
            on=section["on"],
            jurisdiction="US",
            actor=president,
            title=name if person.get("group") else f"{LABELS[kind]}: {name}",
            locator=section["locator"],
            extracted_by=by,
            subject=None if group else name,
            details={**details, "group": True} if group else details,
        )
