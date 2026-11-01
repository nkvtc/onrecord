"""Adapter registry. To add a source: write a module here, then add it to ADAPTERS."""

from .base import Adapter
from .canada_news import CanadaNews
from .doj_clemency import DojClemency
from .doj_clemency_stats import DojClemencyStats
from .eurlex import EurLex
from .eurostat_trade import EurostatTrade
from .fec_form13 import FecForm13
from .fec_inaugural_totals import FecInauguralTotals
from .federal_register import FederalRegister
from .fred_trade import FredTrade
from .gao_reports import GaoReports
from .statcan_trade import StatcanTrade
from .treasury_mts import TreasuryMts
from .usaspending import UsaSpending

ADAPTERS: dict[str, type[Adapter]] = {
    a.name: a
    for a in (
        FederalRegister,
        CanadaNews,
        StatcanTrade,
        FredTrade,
        EurLex,
        EurostatTrade,
        DojClemency,
        DojClemencyStats,
        FecForm13,
        FecInauguralTotals,
        TreasuryMts,
        UsaSpending,
        GaoReports,
    )
}

__all__ = ["ADAPTERS", "Adapter"]
