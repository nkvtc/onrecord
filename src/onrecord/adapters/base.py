"""The adapter contract. One adapter per government data source.

An adapter has exactly two jobs, deliberately split:

    fetch(topic)  -> RawDocument...   talks to the network, decides what is in scope
    parse(raw)    -> ParseResult      pure function: bytes in, records out, no network

Because parse() is pure, every parser can be tested offline against saved fixtures,
and when a parser bug is fixed, `onrecord reparse` rebuilds the database from the raw
archive without hitting a single government server again.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

from ..http import Http
from ..models import ParseResult, RawDocument
from ..topics import Topic


class Adapter(ABC):
    name: ClassVar[str]
    jurisdiction: ClassVar[str]
    description: ClassVar[str]
    # Bump when parse() output changes, so records show which parser made them.
    version: ClassVar[int] = 1
    # Set if the source needs a credential; the CLI skips the adapter when it's missing.
    requires_env: ClassVar[str | None] = None

    def __init__(self, http: Http):
        self.http = http

    @abstractmethod
    def fetch(self, topic: Topic) -> Iterator[RawDocument]: ...

    @classmethod
    @abstractmethod
    def parse(cls, raw: RawDocument) -> ParseResult: ...

    @classmethod
    def extracted_by(cls) -> str:
        return f"rule:{cls.name}@{cls.version}"

    # Helpers ---------------------------------------------------------------

    @classmethod
    def json_raw(cls, source_id: str, url: str, obj) -> RawDocument:
        """Wrap one item from a JSON list API as a raw document.

        Keys are sorted so the same item re-served in a different order doesn't look
        like an edited document. Everything else is kept exactly as served.
        """
        body = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1).encode()
        return RawDocument(
            source=cls.name,
            source_id=source_id,
            url=url,
            fetched_at=datetime.now(UTC),
            content_type="application/json",
            body=body,
        )
