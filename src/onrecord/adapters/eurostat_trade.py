"""Eurostat: EU27 monthly goods trade with a partner country.

Dataset ext_st_eu27_2020sitc ("EU trade since 2020 by SITC"), total of all products,
seasonally and calendar adjusted, million euro. Dissemination API, no key:
https://wikis.ec.europa.eu/display/EUROSTATHELP/API+Statistics+-+data+query
Licence: Eurostat re-use policy (CC BY 4.0).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, Observation, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
DATASET = "ext_st_eu27_2020sitc"
FLOWS = {"EXP": "exports to", "IMP": "imports from"}


class EurostatTrade(Adapter):
    name = "eurostat_trade"
    jurisdiction = "EU"
    description = "Eurostat EU27 monthly goods trade by partner (ext_st_eu27_2020sitc)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        since = f"{topic.since.year - 1}-01"
        for partner in cfg.get("partners", ["US"]):
            for flow in FLOWS:
                params = {
                    "format": "JSON",
                    "lang": "EN",
                    "freq": "M",
                    "geo": "EU27_2020",
                    "partner": partner,
                    "sitc06": "TOTAL",
                    "indic_et": "TRD_VAL_SCA",
                    "stk_flow": flow,
                    "sinceTimePeriod": since,
                }
                resp = self.http.get(f"{API}/{DATASET}", params=params)
                yield self.json_raw(f"{DATASET}:{flow}:{partner}", str(resp.url), resp.json())

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        dims = d["dimension"]
        flow = next(iter(dims["stk_flow"]["category"]["index"]))
        partner_code = next(iter(dims["partner"]["category"]["index"]))
        partner = dims["partner"]["category"]["label"][partner_code]
        # Every dimension but time has size 1, so a value's index is its time index.
        times = {i: t for t, i in dims["time"]["category"]["index"].items()}
        label = f"EU27 {FLOWS[flow]} {partner} (Eurostat, seasonally and calendar adjusted)"
        series_id = f"eurostat:{DATASET}:{flow}:{partner_code}"
        observations = [
            Observation(
                series_id=series_id,
                series_label=label,
                period=date.fromisoformat(times[int(i)] + "-01"),
                value=float(v),
                unit="EUR millions",
                released_at=d.get("updated"),
            )
            for i, v in sorted(d.get("value", {}).items(), key=lambda kv: int(kv[0]))
            if v is not None
        ]
        updated = d.get("updated", "")[:10]
        return ParseResult(
            meta=DocumentMeta(
                title=label,
                jurisdiction="EU",
                publisher="Eurostat",
                doc_type="statistical_series",
                published_on=date.fromisoformat(updated) if updated else None,
                canonical_url=f"https://ec.europa.eu/eurostat/databrowser/view/{DATASET}/default/table",
                citation=f"Eurostat, {DATASET}, {flow}, partner {partner_code}",
                extra={"dataset": DATASET, "flow": flow, "partner": partner_code},
            ),
            observations=observations,
        )
