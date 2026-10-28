"""Topics scope what we collect. Each is a TOML file in /topics.

A topic is a story people want followed ("US–Canada tariffs since 2025") expressed
as per-adapter queries. Adding a topic is a good first contribution: no code needed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

TOPICS_DIR = Path(__file__).resolve().parents[2] / "topics"


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    since: date
    description: str = ""
    sources: dict = field(default_factory=dict)  # adapter name -> its config table
    site: dict = field(default_factory=dict)  # how the website presents this topic

    def config(self, adapter: str) -> dict | None:
        return self.sources.get(adapter)


def load_topic(path: Path) -> Topic:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    meta = {k: data.pop(k) for k in ("id", "title", "since", "description") if k in data}
    site = data.pop("site", {})
    since = meta["since"]
    if isinstance(since, str):
        since = date.fromisoformat(since)
    return Topic(
        id=meta["id"],
        title=meta["title"],
        since=since,
        description=meta.get("description", ""),
        sources=data,
        site=site,
    )


def all_topics(directory: Path = TOPICS_DIR) -> list[Topic]:
    return [load_topic(p) for p in sorted(Path(directory).glob("*.toml"))]
