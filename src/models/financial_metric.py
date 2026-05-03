"""
FinancialMetric domain model — quarterly financial metrics for REITs.

Tracks key REIT-specific financials: FFO, AFFO, same-store NOI growth,
leverage ratios, dividend metrics, and valuation multiples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class FinancialMetric:
    """Quarterly financial metrics for a REIT."""

    reit_ticker: str
    period: str
    fiscal_year: int
    quarter: int
    total_revenue: float = 0.0
    same_store_noi: float = 0.0
    same_store_noi_growth: float = 0.0
    ffo_per_share: float = 0.0
    affo_per_share: float = 0.0
    ffo_growth_yoy: float = 0.0
    net_debt_to_ebitda: float = 0.0
    interest_coverage: float = 0.0
    weighted_avg_cap_rate: float = 0.0
    dividend_per_share: float = 0.0
    dividend_growth_yoy: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    # --- Validation ---

    def __post_init__(self) -> None:
        self.reit_ticker = self.reit_ticker.strip().upper()
        if not self.reit_ticker:
            raise ValueError("REIT ticker must be non-empty")
        if not (1 <= self.quarter <= 4):
            raise ValueError(f"Quarter must be 1-4, got {self.quarter}")
        if self.fiscal_year < 2000:
            raise ValueError(f"Invalid fiscal year: {self.fiscal_year}")

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "reit_ticker": self.reit_ticker,
            "period": self.period,
            "fiscal_year": self.fiscal_year,
            "quarter": self.quarter,
            "total_revenue": self.total_revenue,
            "same_store_noi": self.same_store_noi,
            "same_store_noi_growth": self.same_store_noi_growth,
            "ffo_per_share": self.ffo_per_share,
            "affo_per_share": self.affo_per_share,
            "ffo_growth_yoy": self.ffo_growth_yoy,
            "net_debt_to_ebitda": self.net_debt_to_ebitda,
            "interest_coverage": self.interest_coverage,
            "weighted_avg_cap_rate": self.weighted_avg_cap_rate,
            "dividend_per_share": self.dividend_per_share,
            "dividend_growth_yoy": self.dividend_growth_yoy,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> FinancialMetric:
        """Deserialize from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Derived Metrics ---

    @property
    def affo_payout_ratio(self) -> float:
        """AFFO-based payout ratio."""
        if self.affo_per_share <= 0:
            return 0.0
        return self.dividend_per_share / self.affo_per_share

    @property
    def ffo_payout_ratio(self) -> float:
        """FFO-based payout ratio."""
        if self.ffo_per_share <= 0:
            return 0.0
        return self.dividend_per_share / self.ffo_per_share

    @property
    def affo_yield_spread(self) -> float:
        """Spread between AFFO growth and dividend growth."""
        return self.ffo_growth_yoy - self.dividend_growth_yoy

    @property
    def leverage_rating(self) -> str:
        """Leverage rating based on debt/EBITDA."""
        if self.net_debt_to_ebitda <= 3.0:
            return "A"
        elif self.net_debt_to_ebitda <= 5.0:
            return "B"
        elif self.net_debt_to_ebitda <= 7.0:
            return "C"
        return "D"

    @property
    def dividend_safety(self) -> str:
        """Dividend safety assessment."""
        payout = self.affo_payout_ratio
        if payout <= 0.60:
            return "Very Safe"
        elif payout <= 0.75:
            return "Safe"
        elif payout <= 0.85:
            return "Moderate"
        elif payout <= 0.95:
            return "Risky"
        return "Unsafe"

    def __repr__(self) -> str:
        return (
            f"FinancialMetric(ticker={self.reit_ticker!r}, "
            f"FY{self.fiscal_year}Q{self.quarter}, "
            f"FFO=${self.ffo_per_share:.2f})"
        )
