"""EU legal acts and proposals from EUR-Lex, via the Publications Office SPARQL endpoint.

Endpoint: https://publications.europa.eu/webapi/rdf/sparql (no key).
Each matching act (by English title keywords) is archived as its SPARQL result row.
EUR-Lex content: (c) European Union, reuse authorised (Commission Decision 2011/833/EU).

CELEX numbers say what an act is: first digit = sector (2 international agreements,
3 legislation, 5 preparatory acts, 6 case law, 0 consolidated texts), then the year,
then a type code (R regulation, D decision, PC Commission proposal, ...).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Event, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
BODIES = {
    "COM": "European Commission",
    "TRADE": "European Commission (DG Trade)",
    "CONSIL": "Council of the European Union",
    "EP": "European Parliament",
    "SANTE": "European Commission (DG Health)",
}
TYPES = {"R": "regulation", "D": "decision", "PC": "proposal", "XC": "notice", "C": "notice"}
CELEX_RE = re.compile(r"^(\d)(\d{4})([A-Z]+)(\d+)$")

QUERY = """PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?celex ?date (SAMPLE(?t) AS ?title)
       (GROUP_CONCAT(DISTINCT ?author; separator=" ") AS ?authors)
WHERE {
  ?w cdm:resource_legal_id_celex ?celex ; cdm:work_date_document ?date .
  OPTIONAL { ?w cdm:work_created_by_agent ?author }
  ?e cdm:expression_belongs_to_work ?w ; cdm:expression_title ?t ;
     cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  FILTER(?date >= "%(since)s"^^xsd:date)
  FILTER(%(match)s)
} GROUP BY ?celex ?date ORDER BY ?date LIMIT 2000"""


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


class EurLex(Adapter):
    name = "eurlex"
    jurisdiction = "EU"
    description = "EUR-Lex: EU regulations, decisions and Commission proposals (SPARQL)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        words = [w.lower().replace('"', "") for w in cfg.get("title_any", [])]
        match = " || ".join(f'CONTAINS(LCASE(STR(?t)), "{w}")' for w in words)
        query = QUERY % {"since": topic.since.isoformat(), "match": match or "true"}
        resp = self.http.post(
            ENDPOINT,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        sectors = set(cfg.get("sectors", ["2", "3", "5"]))
        exclude = set(cfg.get("exclude_authors", []))
        for b in resp.json()["results"]["bindings"]:
            celex = b["celex"]["value"]
            m = CELEX_RE.match(celex)
            if not m or m.group(1) not in sectors:
                continue  # skips consolidated texts, corrigenda like "...R(02)", case law
            authors = {a.rsplit("/", 1)[-1] for a in b.get("authors", {}).get("value", "").split()}
            if authors & exclude and not authors & {"TRADE"}:
                continue
            row = {k: v["value"] for k, v in b.items()}
            yield self.json_raw(
                celex, f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}", row
            )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        celex = d["celex"]
        sector, _year, code, _num = CELEX_RE.match(celex).groups()
        authors = [a.rsplit("/", 1)[-1] for a in d.get("authors", "").split()]
        named = [BODIES[a] for a in authors if a in BODIES]
        # Prefer the most specific body (DG Trade over "European Commission").
        publisher = next((BODIES[a] for a in ("TRADE", "CONSIL", "EP") if a in authors), None)
        publisher = publisher or (named[0] if named else "European Union")
        title = _clean(d["title"])
        on = date.fromisoformat(d["date"][:10])
        doc_type = TYPES.get(code, "act")
        if sector == "2":
            doc_type = "international_agreement"
        kind = (
            "proposed"
            if code == "PC"
            else "adopted"
            if sector == "3" and code in "RD"
            else "published"
        )
        url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
        return ParseResult(
            meta=DocumentMeta(
                title=title,
                jurisdiction="EU",
                publisher=publisher,
                doc_type=doc_type,
                published_on=on,
                canonical_url=url,
                citation=f"CELEX {celex}",
                extra={"celex": celex, "authors": authors},
            ),
            events=[
                Event(
                    kind=kind,
                    on=on,
                    jurisdiction="EU",
                    actor=publisher,
                    title=title,
                    locator=f"CELEX {celex}; EUR-Lex work date (cdm:work_date_document)",
                    extracted_by=cls.extracted_by(),
                )
            ],
        )
