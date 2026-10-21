"""The record types everything else is built from.

Four layers, kept apart on purpose:

- RawDocument: exactly what a government server returned, byte for byte. Never edited.
- Event:       something that officially happened (signed, published, took effect, ...).
- Claim:       something an official body *said*. Not proof that it happened.
- Observation: a number from an official statistical release (trade flows, prices, ...).

Every Event, Claim and Observation points back at the RawDocument it came from,
plus a `locator` saying where inside that document to look. If a record can't say
where it came from, it doesn't get stored.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class RawDocument:
    source: str  # adapter name, e.g. "federal_register"
    source_id: str  # the source's own stable id, e.g. FR document number
    url: str  # where it was fetched from
    fetched_at: datetime
    content_type: str  # "application/json", "text/plain", ...
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class DocumentMeta:
    """Human-facing description of a raw document, produced by an adapter's parser."""

    title: str
    jurisdiction: str  # ISO-ish: "US", "CA", "EU"
    publisher: str  # "Executive Office of the President", "Department of Finance Canada"
    doc_type: str  # "proclamation", "executive_order", "news_release", "statistical_release"
    published_on: date | None
    canonical_url: str  # the page a human should open to check us
    citation: str | None = None  # e.g. "90 FR 8471"
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    kind: str  # see EVENT_KINDS
    on: date
    jurisdiction: str
    actor: str
    title: str
    locator: str  # where in the source document this is stated
    extracted_by: str  # "rule:<adapter>@<version>" or later "llm:<model>"


EVENT_KINDS = {
    "signed",  # a head of government / minister signed it
    "published",  # appeared in an official gazette / register
    "effective",  # legally in force from this date
    "announced",  # announced but not yet a legal instrument
    "suspended",
    "revoked",
    "challenged",  # court challenge filed
    "struck_down",
}


@dataclass(frozen=True)
class Claim:
    speaker: str
    said_on: date
    jurisdiction: str
    text: str  # quoted or source-provided summary, never our paraphrase
    locator: str
    extracted_by: str


@dataclass(frozen=True)
class Observation:
    series_id: str  # stable id, e.g. "statcan:12100011:1.2.1.1.2"
    series_label: str  # "Canada exports to United States (customs basis, unadjusted)"
    period: date  # first day of the reference period
    value: float
    unit: str  # "CAD millions"
    released_at: str | None  # when the agency published this value (revisions happen!)


@dataclass
class ParseResult:
    meta: DocumentMeta
    events: list[Event] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
