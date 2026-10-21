"""Statistics Canada: monthly merchandise trade by principal trading partner.

Table 12-10-0011-01. Web Data Service docs:
https://www.statcan.gc.ca/en/developers/wds/user-guide
No key required. Statistics Canada Open Licence.

Defaults to the balance-of-payments basis, seasonally adjusted, because those are the
headline figures StatCan publishes and the press quotes. Both are configurable, and
the basis/adjustment is written into every series label so nobody compares unlike
numbers by accident.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"
PRODUCT_ID = 12100011
TRADE = {1: "imports from", 2: "exports to", 3: "trade balance with"}
BASIS = {1: "customs basis", 2: "balance of payments basis"}
ADJUSTMENT = {1: "unadjusted", 2: "seasonally adjusted"}
# StatCan scalarFactorCode -> word
SCALAR = {0: "", 3: "thousands", 6: "millions", 9: "billions"}


class StatcanTrade(Adapter):
    name = "statcan_trade"
    jurisdiction = "CA"
    description = "Statistics Canada monthly merchandise trade by partner (table 12-10-0011)"

    def _partner_ids(self) -> dict[str, int]:
        resp = self.http.post(f"{WDS}/getCubeMetadata", json=[{"productId": PRODUCT_ID}])
        dims = resp.json()[0]["object"]["dimension"]
        partners = next(d for d in dims if d["dimensionPositionId"] == 5)
        return {m["memberNameEn"]: m["memberId"] for m in partners["member"]}

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        basis = cfg.get("basis", 2)
        adjustment = cfg.get("adjustment", 2)
        months = int(cfg.get("months", 48))
        ids = self._partner_ids()
        for partner in cfg.get("partners", ["United States"]):
            if partner not in ids:
                raise ValueError(f"Unknown StatCan partner {partner!r}; known: {sorted(ids)}")
            for trade in (1, 2):
                coord = f"1.{trade}.{basis}.{adjustment}.{ids[partner]}.0.0.0.0.0"
                resp = self.http.post(
                    f"{WDS}/getDataFromCubePidCoordAndLatestNPeriods",
                    json=[{"productId": PRODUCT_ID, "coordinate": coord, "latestN": months}],
                )
                result = resp.json()[0]
                if result.get("status") != "SUCCESS":
                    raise RuntimeError(f"StatCan returned {result} for {coord}")
                item = {
                    "product_id": PRODUCT_ID,
                    "coordinate": coord,
                    "labels": {
                        "partner": partner,
                        "trade": TRADE[trade],
                        "basis": BASIS[basis],
                        "adjustment": ADJUSTMENT[adjustment],
                    },
                    "response": result["object"],
                }
                yield self.json_raw(
                    f"{PRODUCT_ID}:{coord}",
                    f"{WDS}/getDataFromCubePidCoordAndLatestNPeriods",
                    item,
                )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        labels = d["labels"]
        points = d["response"].get("vectorDataPoint", [])
        vector = d["response"].get("vectorId")
        label = (
            f"Canada {labels['trade']} {labels['partner']} "
            f"({labels['basis']}, {labels['adjustment']})"
        )
        series_id = f"statcan:{d['product_id']}:{d['coordinate']}"
        observations = []
        for p in points:
            if p.get("value") is None:
                continue  # suppressed / not available: absence is not zero
            scale = SCALAR.get(p.get("scalarFactorCode", 0), "")
            observations.append(
                Observation(
                    series_id=series_id,
                    series_label=label,
                    period=date.fromisoformat(p["refPer"]),
                    value=float(p["value"]),
                    unit=f"CAD {scale}".strip(),
                    released_at=p.get("releaseTime"),
                )
            )
        latest = max((o.released_at or "" for o in observations), default="")
        return ParseResult(
            meta=DocumentMeta(
                title=label,
                jurisdiction="CA",
                publisher="Statistics Canada",
                doc_type="statistical_series",
                published_on=date.fromisoformat(latest[:10]) if latest else None,
                canonical_url=f"https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={PRODUCT_ID}01",
                citation=f"Statistics Canada, Table 12-10-0011-01, vector v{vector}",
                extra={"vector_id": vector, "coordinate": d["coordinate"], **labels},
            ),
            observations=observations,
        )
