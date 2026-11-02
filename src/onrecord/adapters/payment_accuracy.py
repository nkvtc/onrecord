"""PaymentAccuracy.gov (OMB): agencies' own estimates of improper payments, by program.

Agencies must estimate improper payments under the Payment Integrity Information Act of
2019 and report them to OMB, which publishes one cumulative spreadsheet a year at
https://paymentaccuracy.gov/resources (no key). US federal data, public domain.

The newest dataset covers every year back to 2004, so only that one file is fetched;
the file name is read from the resources page. Amounts are in USD millions as published.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime

from ..models import DocumentMeta, ParseResult, RawDocument
from ..topics import Topic
from .base import Adapter

SITE = "https://paymentaccuracy.gov"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET = "All Program Results"
# Spreadsheet column -> row key. Headers are matched after collapsing whitespace.
COLUMNS = {
    "Agency": "agency",
    "Program Name": "program",
    "Fiscal Year": "fiscal_year",
    "Outlays Amount ($M)": "outlays",
    "Improper Payment Amount ($M)": "improper",
    "Unknown Payment Amount ($M)": "unknown",
    "Improper Payment and Unknown Payment Amount ($M)": "improper_and_unknown",
    "Improper Payment and Unknown Payment Rate": "rate",
    "Total Overpayments Amount ($M)": "overpayments",
    "Overpayments within the Agency Control Amount ($M)": "overpayments_agency_control",
    "Underpayment Amount ($M)": "underpayments",
    "Technically Improper Payment Amount ($M)": "technically_improper",
    "Confidence Interval for the estimate": "confidence",
    "Margin of Error for the estimate": "margin_of_error",
}


class PaymentAccuracy(Adapter):
    name = "payment_accuracy"
    jurisdiction = "US"
    description = "PaymentAccuracy.gov: improper payment estimates by federal program (OMB)"

    def fetch(self, topic: Topic) -> Iterator[RawDocument]:
        page = self.http.get(f"{SITE}/resources").text
        years = re.findall(r'data-file-name="FY(\d{4})_Dataset\.xlsx"', page)
        if not years:
            raise RuntimeError("PaymentAccuracy.gov resources page: no dataset links found")
        name = f"FY{max(years)}_Dataset.xlsx"
        resp = self.http.get(f"{SITE}/assets/files/{name}")
        yield RawDocument(
            source=self.name,
            source_id=f"dataset:FY{max(years)}",
            url=str(resp.url),
            fetched_at=datetime.now(UTC),
            content_type=XLSX,
            body=resp.content,
        )

    @classmethod
    def parse(cls, raw: RawDocument) -> ParseResult:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw.body), read_only=True, data_only=True)
        # The published sheet name carries a trailing space; match it loosely.
        ws = next(w for w in wb.worksheets if w.title.strip() == SHEET)
        sheet = ws.iter_rows(values_only=True)
        header = [re.sub(r"\s+", " ", str(h or "")).strip() for h in next(sheet)]
        index = {COLUMNS[h]: i for i, h in enumerate(header) if h in COLUMNS}
        rows = []
        for values in sheet:
            row = {k: values[i] for k, i in index.items()}
            if not row.get("program") or not isinstance(row.get("fiscal_year"), int):
                continue
            for k, v in row.items():
                if isinstance(v, float):
                    row[k] = round(v, 6)
                elif v is not None and not isinstance(v, (int, str)):
                    row[k] = str(v)
            rows.append(row)
        wb.close()
        dataset_year = int(re.search(r"(\d{4})", raw.source_id).group(1))
        return ParseResult(
            meta=DocumentMeta(
                title=f"Improper payment estimates by program, FY{dataset_year} dataset",
                jurisdiction="US",
                publisher="Office of Management and Budget (PaymentAccuracy.gov)",
                doc_type="dataset",
                published_on=date(dataset_year, 9, 30),
                canonical_url=f"{SITE}/resources",
                citation=f"PaymentAccuracy.gov, FY{dataset_year} dataset, sheet {SHEET!r}",
                extra={"kind": "programs", "dataset_year": dataset_year, "rows": rows},
            )
        )
