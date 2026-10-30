"""DOJ Office of the Pardon Attorney: clemency statistics by president, back to McKinley.

https://www.justice.gov/pardon/clemency-statistics has one table per president, by
fiscal year, with petitions received, granted (pardons, commutations, remissions or
respites) and denied. These count clemency granted *on petitions*: grants made by
proclamation to a class of people (e.g. Carter's draft-evader pardon, Biden's marijuana
possession pardons) are not in these tables, and labels on the site say so.

A president's current term appears only once DOJ adds it.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

PARDON = {"P", "Pardon", "Pardons"}
COMMUTATION = {"C", "Commutation", "Commutations"}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _num(s: str) -> int:
    s = s.replace(",", "").strip()
    return int(s) if s.isdigit() else 0


def _expand(row: str) -> list[tuple[str, int]]:
    """Cells of a table row as (text, colspan)."""
    out = []
    for attrs, body in re.findall(r"<t[hd]([^>]*)>(.*?)</t[hd]>", row, re.S):
        span = re.search(r'colspan="?(\d+)', attrs)
        out.append((_text(body), int(span.group(1)) if span else 1))
    return out


def parse_table(table: str) -> dict | None:
    """Pardons and commutations granted, from one president's table."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    if len(rows) < 3:
        return None
    header, sub = _expand(rows[0]), _expand(rows[1])
    # Lay the top header out across columns, then find the span of "Granted".
    top: list[str] = []
    for text, span in header:
        top.extend([text] * span)
    if "Fiscal Year" not in top[0]:
        return None
    granted = [i for i, t in enumerate(top) if "Granted" in t]
    if not granted:
        return None
    labels = [t for t, span in sub for _ in range(span)]
    # Newer tables label every column after the first (P, C, P, C, ...); older ones
    # label only the "Granted" columns (Pardon, Commutation, Remission, ...).
    if len(labels) == len(top) - 1:
        codes = [""] + labels
    elif len(labels) == len(granted):
        codes = [""] * len(top)
        for i, label in zip(granted, labels, strict=True):
            codes[i] = label
    else:
        return None  # unknown layout: report nothing rather than a wrong number
    pardon_col = next((i for i in granted if i < len(codes) and codes[i] in PARDON), None)
    commute_col = next((i for i in granted if i < len(codes) and codes[i] in COMMUTATION), None)

    years, total = [], None
    for r in rows[2:]:
        cells = [t for t, span in _expand(r) for _ in range(span)]
        if not cells:
            continue
        label = cells[0]
        values = {
            "pardons": _num(cells[pardon_col]) if pardon_col and pardon_col < len(cells) else 0,
            "commutations": _num(cells[commute_col])
            if commute_col and commute_col < len(cells)
            else 0,
        }
        if label.lower().startswith("total"):
            total = {"label": label, **values}
        else:
            m = re.match(r"(\d{4})", label)
            if m:
                years.append({"fiscal_year": int(m.group(1)), "label": label, **values})
    if not years:
        return None
    if total is None:  # older tables have no total row
        total = {
            "label": "Sum of fiscal years",
            "pardons": sum(y["pardons"] for y in years),
            "commutations": sum(y["commutations"] for y in years),
        }
    months = re.search(r"([\d.]+)\s*mos", total["label"])
    return {
        "first_fiscal_year": years[0]["fiscal_year"],
        "last_fiscal_year": years[-1]["fiscal_year"],
        "months": float(months.group(1)) if months else None,
        "pardons": total["pardons"],
        "commutations": total["commutations"],
        "total_row": total["label"],
    }


class DojClemencyStats(Adapter):
    name = "doj_clemency_stats"
    jurisdiction = "US"
    description = "DOJ Office of the Pardon Attorney: clemency statistics by president"

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
        body = page[page.find("field_body") :] if "field_body" in page else page
        presidents = []
        for part in re.split(r"<h[23][^>]*>", body)[1:]:
            head, _, rest = part.partition("</h")
            name = _text(head)
            table = re.search(r"<table.*?</table>", rest, re.S)
            if not name or not table:
                continue
            stats = parse_table(table.group(0))
            if stats:
                presidents.append({"president": name, **stats})

        observations = []
        for p in presidents:
            for kind in ("pardons", "commutations"):
                observations.append(
                    Observation(
                        series_id=f"doj:clemency_granted:{kind}",
                        series_label=f"Clemency petitions granted ({kind}), by president",
                        # One point per president, keyed by their first fiscal year.
                        period=date(p["first_fiscal_year"], 1, 1),
                        value=float(p[kind]),
                        unit="grants",
                        released_at=None,
                    )
                )
        return ParseResult(
            meta=DocumentMeta(
                title="Clemency statistics by president",
                jurisdiction="US",
                publisher="US Department of Justice, Office of the Pardon Attorney",
                doc_type="statistical_table",
                published_on=None,
                canonical_url=raw.url,
                extra={"presidents": presidents},
            ),
            observations=observations,
        )
