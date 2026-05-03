"""
Scope.Sentinel — REIT Analytics Platform on AWS

Domain models for REIT master data, properties, financial metrics,
SEC filings, market indicators, and composite signal scores.
"""

from src.models.reit import REIT
from src.models.property import Property
from src.models.financial_metric import FinancialMetric
from src.models.sec_filing import SECFiling
from src.models.market_indicator import MarketIndicator
from src.models.reit_signal import REITSignal

__all__ = [
    "REIT",
    "Property",
    "FinancialMetric",
    "SECFiling",
    "MarketIndicator",
    "REITSignal",
]
