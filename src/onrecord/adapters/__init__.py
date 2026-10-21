"""Adapter registry. To add a source: write a module here, then add it to ADAPTERS."""

from .base import Adapter
from .canada_news import CanadaNews
from .federal_register import FederalRegister
from .statcan_trade import StatcanTrade

ADAPTERS: dict[str, type[Adapter]] = {
    a.name: a for a in (FederalRegister, CanadaNews, StatcanTrade)
}

__all__ = ["ADAPTERS", "Adapter"]
