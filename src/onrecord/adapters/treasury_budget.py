"""US Treasury Monthly Treasury Statement: the whole budget, by fiscal year.

Fiscal Data API, no key: https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/
US federal data, public domain.

Two tables, fetched as each fiscal year's year-to-date figures (October to September):

  Table 9  receipts by source and net outlays by budget function (what the money is for)
  Table 5  net outlays by agency, with the larger bureaus inside each agency

A finished fiscal year is the September statement. The year in progress is the latest
statement and says how many months it covers. Net outlays are spending minus offsetting
collections, so a line can be negative (FDIC premiums, loan repayments).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

from ..models import DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts"
TABLES = {9: "mts_table_9", 5: "mts_table_5"}
# Only the columns the parser reads, so each archived year stays small.
COMMON = (
    "record_date,classification_id,parent_id,classification_desc,sequence_level_nbr,print_order_nbr"
)
FIELDS = {9: f"{COMMON},current_fytd_rcpt_outly_amt", 5: f"{COMMON},current_fytd_net_outly_amt"}
PAGE = "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"


def _amount(v) -> float | None:
    return None if v in (None, "", "null") else float(v)


class TreasuryBudget(Adapter):
    name = "treasury_budget"
    jurisdiction = "US"
    description = "US Treasury Monthly Treasury Statement: receipts, outlays by function and agency"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        cfg = topic.config(self.name) or {}
        latest = self.http.get(
            f"{API}/{TABLES[9]}", params={"sort": "-record_date", "page[size]": "1"}
        ).json()["data"][0]["record_date"]
        last = date.fromisoformat(latest)
        last_fy = last.year + (1 if last.month >= 10 else 0)
        for fy in range(cfg.get("first_year", 2015), last_fy + 1):
            record_date = f"{fy}-09-30" if fy < last_fy else latest
            for table, path in TABLES.items():
                params = {
                    "filter": f"record_date:eq:{record_date}",
                    "fields": FIELDS[table],
                    "page[size]": "2000",
                }
                resp = self.http.get(f"{API}/{path}", params=params)
                item = {"table": table, "fiscal_year": fy, "response": resp.json()}
                yield self.json_raw(f"mts{table}:FY{fy}", str(resp.url), item)

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        d = json.loads(raw.body)
        table, fy = d["table"], d["fiscal_year"]
        rows = sorted(d["response"].get("data", []), key=lambda r: int(r["print_order_nbr"]))
        record_date = rows[0]["record_date"] if rows else f"{fy}-09-30"
        end = date.fromisoformat(record_date)
        months = (end.month - 9) % 12 or 12
        extra = {"kind": f"mts{table}", "fiscal_year": fy, "through": record_date, "months": months}
        extra.update(cls._table9(rows) if table == 9 else cls._table5(rows))
        span = "" if months == 12 else f", {months} months through {end:%B %Y}"
        what = "receipts and outlays by function" if table == 9 else "outlays by agency"
        return ParseResult(
            meta=DocumentMeta(
                title=f"Federal {what}, FY{fy}{span}",
                jurisdiction="US",
                publisher="US Department of the Treasury, Bureau of the Fiscal Service",
                doc_type="dataset",
                published_on=end,
                canonical_url=PAGE,
                citation=f"Monthly Treasury Statement, Table {table}, FY{fy} year to date",
                extra=extra,
            )
        )

    @staticmethod
    def _table9(rows: list[dict]) -> dict:
        names = {r["classification_id"]: r["classification_desc"] for r in rows}
        lines, totals = [], {}
        for r in rows:
            amount = _amount(r["current_fytd_rcpt_outly_amt"])
            if amount is None:
                continue
            section = names.get(r["parent_id"], "")
            group = names.get(r["parent_id"]) if r["sequence_level_nbr"] == "3" else None
            if r["sequence_level_nbr"] == "3":
                # Sub-lines (social insurance) sit under a level-2 header; find its section.
                header = next(x for x in rows if x["classification_id"] == r["parent_id"])
                section = names.get(header["parent_id"], "")
            key = "receipts" if section == "Receipts" else "outlays"
            if r["classification_desc"] == "Total":
                totals[key] = amount
                continue
            line = {"section": key, "name": r["classification_desc"], "amount": amount}
            if group:
                line["group"] = group.rstrip(":")
            lines.append(line)
        return {"rows": lines, "totals": totals}

    @staticmethod
    def _table5(rows: list[dict]) -> dict:
        agencies, totals, current = [], {}, None
        for r in rows:
            desc, level = r["classification_desc"], r["sequence_level_nbr"]
            amount = _amount(r["current_fytd_net_outly_amt"])
            if desc == "Total Outlays":
                totals["outlays"] = amount
                current = None
            elif desc.startswith("Total Surplus"):
                totals["surplus_or_deficit"] = amount
            elif level == "1" and amount is None:
                current = {"name": desc.rstrip(":"), "amount": None, "bureaus": []}
                agencies.append(current)
            elif current and desc.startswith("Total--") and amount is not None:
                name = desc.removeprefix("Total--")
                if level == "2":
                    current["amount"] = amount
                elif level == "3":
                    current["bureaus"].append({"name": name, "amount": amount})
        return {"rows": [a for a in agencies if a["amount"] is not None], "totals": totals}
