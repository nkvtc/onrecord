"""Bills Congress has voted on: what each would change, and how the votes split.

Two official sources, no key:

  House roll calls  https://clerk.house.gov/evs/{year}/roll{nnn}.xml  (Office of the Clerk)
  Bill status       https://www.govinfo.gov/bulkdata/BILLSTATUS/      (GPO, from Congress.gov)

A roll call file lists every member's vote (~90KB); only its header is used (question,
bill, result, totals by party), so only its first bytes are fetched with an HTTP range
request and archived. The bill status file has the Congressional Research Service
summary, the sponsor, and every action, including each chamber's vote counts as stated
in the action text. senate.gov refuses automated requests, so Senate votes come from
those action texts, and bills are found through House roll calls: a bill the Senate
voted on but the House never has is not included.
US federal data, public domain.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import UTC, date, datetime
from html import unescape

import httpx

from ..models import DocumentMeta, Event, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

CLERK = "https://clerk.house.gov/evs"
BILLSTATUS = "https://www.govinfo.gov/bulkdata/BILLSTATUS"
# The header with the totals ends well inside the first 8KB of every roll call file.
HEAD_BYTES = 8000
# Bill types that can become law; resolutions of one chamber (rules, H RES) are left out.
LEGIS = {"H R": "hr", "S": "s", "H J RES": "hjres", "S J RES": "sjres"}
LABEL = {"hr": "H.R.", "s": "S.", "hjres": "H.J.Res.", "sjres": "S.J.Res."}
URL_TYPE = {
    "hr": "house-bill",
    "s": "senate-bill",
    "hjres": "house-joint-resolution",
    "sjres": "senate-joint-resolution",
}
# Library of Congress action prefixes that record a floor decision on the bill itself.
FLOOR = (
    "Passed/agreed to in",
    "Failed of passage/not agreed to in",
    "Resolving differences",
    "Passed Senate",
    "Passed House",
)
# House roll call questions that decide a bill itself, not a procedural step. Those votes
# are archived in full, with every member's vote; the rest keep only their header.
PASSAGE = (
    "Passage",
    "Suspend the Rules and Pass",
    "Senate Amendment",
    "Conference Report",
    "Objections of the President",
)
VOTE = {"Aye": "Yea", "No": "Nay"}  # the Clerk uses both spellings
CHAMBER = {"House": "US House of Representatives", "Senate": "US Senate"}
# "Yea-Nay Vote. 51 - 50", "Yeas and Nays: 215 - 214", "recorded vote: 218 - 214"; not page
# ranges such as "CR S4797-4798".
TALLY = re.compile(r"(?:Vote\.|Nays:|vote:)\s*(\d+)\s*-\s*(\d+)")


def bill_key(legis_num: str) -> tuple[str, int] | None:
    m = re.fullmatch(r"(H R|S|H J RES|S J RES) (\d+)", (legis_num or "").strip())
    return (LEGIS[m.group(1)], int(m.group(2))) if m else None


def decides_bill(question: str) -> bool:
    return any(p in question for p in PASSAGE) and "Recommit" not in question


def _text(el, path: str) -> str:
    return (el.findtext(path) or "").strip()


def _strip_html(s: str) -> str:
    s = re.sub(r"</p>|<br\s*/?>|</li>", "\n", s)
    s = unescape(re.sub(r"<[^>]+>", "", s))
    return "\n".join(line.strip() for line in s.splitlines() if line.strip())


class CongressBills(Adapter):
    name = "congress_bills"
    jurisdiction = "US"
    description = "House roll calls and Congress.gov bill status: votes, summaries, outcomes"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        congress = cfg.get("congress", 119)
        first = 1789 + 2 * (congress - 1)
        bills: dict[tuple[str, int], None] = {}
        for year in (first, first + 1):
            if year > datetime.now(UTC).year:
                break
            n, misses = 1, 0
            # Roll calls are numbered from 1 each session; stop after two missing numbers.
            while misses < 2:
                url = f"{CLERK}/{year}/roll{n:03d}.xml"
                n += 1
                try:
                    resp = self.http.get(url, headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"})
                except httpx.HTTPStatusError as e:
                    if e.response.status_code != 404:
                        raise
                    misses += 1
                    continue
                if b"<rollcall-vote" not in resp.content[:500]:
                    # Numbers past the last vote answer with an error stub, not a 404.
                    misses += 1
                    continue
                misses = 0
                head = self._roll(resp.content)
                key = bill_key(head.get("legis_num", ""))
                if key:
                    bills[key] = None
                    if decides_bill(head.get("question", "")):
                        resp = self.http.get(url)
                yield self._raw(f"house:{year}:{n - 1}", url, resp.content)
        for kind, number in bills:
            url = f"{BILLSTATUS}/{congress}/{kind}/BILLSTATUS-{congress}{kind}{number}.xml"
            try:
                resp = self.http.get(url)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:  # not yet in the bulk data
                    continue
                raise
            yield self._raw(f"bill:{congress}{kind}{number}", url, resp.content)

    @classmethod
    def _raw(cls, source_id: str, url: str, body: bytes) -> RawDocument:
        return RawDocument(
            source=cls.name,
            source_id=source_id,
            url=url,
            fetched_at=datetime.now(UTC),
            content_type="application/xml",
            body=body,
        )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        if b"<rollcall-vote" in raw.body[:500]:
            return cls._parse_roll(raw)
        return cls._parse_bill(raw)

    # House roll calls ------------------------------------------------------

    @staticmethod
    def _roll(body: bytes) -> dict:
        # Most archived files stop partway through the member list (a range request), so
        # the header is parsed on its own; members are read only when the file is whole.
        s = body.decode("utf-8", errors="replace")
        end = s.find("</vote-metadata>")
        if end < 0:
            return {}
        meta = ET.fromstring(s[s.find("<vote-metadata>") : end + len("</vote-metadata>")])
        parties = []
        for p in meta.findall("vote-totals/totals-by-party"):
            parties.append(
                {
                    "party": _text(p, "party"),
                    "yea": int(_text(p, "yea-total") or 0),
                    "nay": int(_text(p, "nay-total") or 0),
                    "present": int(_text(p, "present-total") or 0),
                    "not_voting": int(_text(p, "not-voting-total") or 0),
                }
            )
        total = meta.find("vote-totals/totals-by-vote")
        members = None
        if "</rollcall-vote>" in s:
            root = ET.fromstring(s[s.find("<rollcall-vote") :])
            members = []
            for rv in root.findall("vote-data/recorded-vote"):
                leg = rv.find("legislator")
                vote = _text(rv, "vote")
                members.append(
                    {
                        "id": leg.get("name-id"),
                        "name": (leg.text or "").strip(),
                        "party": leg.get("party"),
                        "state": leg.get("state"),
                        "vote": VOTE.get(vote, vote),
                    }
                )
        return {
            "majority": _text(meta, "majority") or None,
            "roll": int(_text(meta, "rollcall-num") or 0),
            "congress": int(_text(meta, "congress") or 0),
            "legis_num": _text(meta, "legis-num"),
            "question": _text(meta, "vote-question"),
            "vote_type": _text(meta, "vote-type"),
            "result": _text(meta, "vote-result"),
            "date": datetime.strptime(_text(meta, "action-date"), "%d-%b-%Y").date().isoformat(),
            "description": _text(meta, "vote-desc"),
            "yea": int(_text(total, "yea-total") or 0) if total is not None else None,
            "nay": int(_text(total, "nay-total") or 0) if total is not None else None,
            "rows": parties,
            "members": members,
        }

    @classmethod
    def _parse_roll(cls, raw: RawDocument) -> ParseResult:
        v = cls._roll(raw.body)
        key = bill_key(v.get("legis_num", ""))
        on = date.fromisoformat(v["date"])
        return ParseResult(
            meta=DocumentMeta(
                title=f"House roll call {v['roll']} ({on.year}): {v['question']}, "
                f"{v['legis_num'] or 'no measure'}",
                jurisdiction="US",
                publisher="Office of the Clerk, US House of Representatives",
                doc_type="roll_call_vote",
                published_on=on,
                canonical_url=raw.url,
                citation=f"Roll no. {v['roll']}, {on.year}",
                extra={"kind": "house_vote", "bill": f"{key[0]}{key[1]}" if key else None, **v},
            )
        )

    # Bill status -----------------------------------------------------------

    @classmethod
    def _parse_bill(cls, raw: RawDocument) -> ParseResult:
        b = ET.fromstring(raw.body).find("bill")
        kind, number, congress = (
            _text(b, "type").lower(),
            int(_text(b, "number")),
            _text(b, "congress"),
        )
        label = f"{LABEL.get(kind, kind.upper())} {number}"
        sponsor = b.find("sponsors/item")
        # The name people use: the popular title, else a short title for the whole bill (not
        # those of sections that were once separate bills), else Congress.gov's display title.
        titles = [(_text(t, "titleType"), _text(t, "title")) for t in b.findall("titles/item")]
        short = next(
            (t for k, t in titles if k == "Popular Titles"),
            next(
                (t for k, t in titles if k.startswith("Short Title") and "portion" not in k),
                next((t for k, t in titles if k == "Display Title"), ""),
            ),
        )
        floor, events = [], []
        introduced = _text(b, "introducedDate")
        if introduced:
            events.append(
                Event(
                    kind="proposed",
                    on=date.fromisoformat(introduced),
                    jurisdiction="US",
                    actor=_text(sponsor, "fullName") if sponsor is not None else "Congress",
                    title=f"{label} introduced",
                    locator="actions: introduced",
                    extracted_by=cls.extracted_by(),
                )
            )
        for a in b.findall("actions/item"):
            text = _text(a, "text")
            if _text(a, "sourceSystem/name") != "Library of Congress":
                continue
            on = date.fromisoformat(_text(a, "actionDate"))
            if text.startswith(FLOOR):
                chamber = "Senate" if "Senate" in text.split(":")[0] else "House"
                m = TALLY.search(text)
                failed = text.startswith("Failed") or " Failed " in text or "not agreed to" in text
                floor.append(
                    {
                        "date": on.isoformat(),
                        "chamber": chamber,
                        "text": text,
                        "yea": int(m.group(1)) if m else None,
                        "nay": int(m.group(2)) if m else None,
                        "passed": not failed,
                        "roll": next(
                            (
                                _text(r, "rollNumber")
                                for r in a.findall("recordedVotes/recordedVote")
                            ),
                            None,
                        ),
                    }
                )
                if not failed:
                    events.append(
                        Event(
                            kind="passed",
                            on=on,
                            jurisdiction="US",
                            actor=CHAMBER[chamber],
                            title=text,
                            locator=f"actions: {on.isoformat()}",
                            extracted_by=cls.extracted_by(),
                        )
                    )
            elif text.startswith(("Became Public Law", "Vetoed by President")):
                events.append(
                    Event(
                        kind="adopted" if text.startswith("Became") else "vetoed",
                        on=on,
                        jurisdiction="US",
                        actor="Congress"
                        if text.startswith("Became")
                        else "President of the United States",
                        title=text,
                        locator=f"actions: {on.isoformat()}",
                        extracted_by=cls.extracted_by(),
                    )
                )
        # The same action can be listed more than once (e.g. under two action codes).
        floor = sorted({(f["date"], f["text"]): f for f in floor}.values(), key=lambda f: f["date"])
        events = list({(e.kind, e.on, e.title): e for e in events}.values())
        summaries = sorted(b.findall("summaries/summary"), key=lambda s: _text(s, "actionDate"))
        summary = None
        if summaries:
            s = summaries[-1]
            text = _strip_html(_text(s, "text"))
            first, _, rest = text.partition("\n")
            # CRS summaries open with the bill's name on its own line; the substance follows.
            if rest and len(first) < 150 and not first.endswith("."):
                text = rest
            summary = {
                "version": _text(s, "actionDesc"),
                "date": _text(s, "actionDate"),
                "text": text,
            }
        law = b.find("laws/item")
        vetoed = any(e.kind == "vetoed" for e in events)
        extra = {
            "kind": "bill",
            "congress": int(congress),
            "type": kind,
            "number": number,
            "label": label,
            "title": _text(b, "title"),
            "short_title": short or None,
            "sponsor": _text(sponsor, "fullName") if sponsor is not None else None,
            "sponsor_party": _text(sponsor, "party") if sponsor is not None else None,
            "introduced": introduced or None,
            "policy_area": _text(b, "policyArea/name") or None,
            "cbo": [
                {
                    "url": _text(c, "url"),
                    "date": _text(c, "pubDate")[:10],
                    "note": _text(c, "description"),
                }
                for c in b.findall("cboCostEstimates/item")
            ],
            "latest_action": {
                "date": _text(b, "latestAction/actionDate"),
                "text": _text(b, "latestAction/text"),
            },
            "law": f"{_text(law, 'type')} {_text(law, 'number')}" if law is not None else None,
            "vetoed": vetoed,
            "summary": summary,
            "abstract": summary["text"].split("\n")[0][:600] if summary else None,
            "rows": floor,
        }
        congress_url = (
            f"https://www.congress.gov/bill/{congress}th-congress/"
            f"{URL_TYPE.get(kind, kind)}/{number}"
        )
        return ParseResult(
            meta=DocumentMeta(
                title=f"{label}: {short or _text(b, 'title')}",
                jurisdiction="US",
                publisher="US Congress",
                doc_type="bill",
                published_on=date.fromisoformat(extra["latest_action"]["date"])
                if extra["latest_action"]["date"]
                else None,
                canonical_url=congress_url,
                citation=f"{label}, {congress}th Congress",
                extra=extra,
            ),
            events=events,
        )
