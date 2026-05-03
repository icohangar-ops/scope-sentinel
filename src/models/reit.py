"""
REIT domain model — master data for Real Estate Investment Trusts.

Tracks sector classification, market data, property portfolio metrics,
dividend metrics, and fundamental data for each REIT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class REITSector(str, Enum):
    """REIT sector classifications per NAREIT."""
    RETAIL = "Retail"
    OFFICE = "Office"
    INDUSTRIAL = "Industrial"
    RESIDENTIAL = "Residential"
    HEALTHCARE = "Healthcare"
    DATA_CENTER = "DataCenter"
    INFRASTRUCTURE = "Infrastructure"
    SPECIALTY = "Specialty"


# Seed data: 12 major REITs
SEED_REITS: List[Dict] = [
    {"ticker": "O", "name": "Realty Income", "sector": REITSector.RETAIL, "sub_sector": "Net Lease",
     "market_cap": 45_000_000_000, "ipo_year": 1994, "property_count": 13500,
     "total_sqft": 280_000_000, "geographic_focus": "US & Europe",
     "dividend_yield": 5.8, "payout_ratio": 0.76, "latest_ffo_per_share": 4.05},
    {"ticker": "AMT", "name": "American Tower", "sector": REITSector.INFRASTRUCTURE, "sub_sector": "Tower",
     "market_cap": 110_000_000_000, "ipo_year": 2012, "property_count": 226000,
     "total_sqft": 0, "geographic_focus": "Global",
     "dividend_yield": 3.4, "payout_ratio": 0.62, "latest_ffo_per_share": 9.82},
    {"ticker": "PLD", "name": "Prologis", "sector": REITSector.INDUSTRIAL, "sub_sector": "Logistics",
     "market_cap": 120_000_000_000, "ipo_year": 1998, "property_count": 5200,
     "total_sqft": 1_200_000_000, "geographic_focus": "Global",
     "dividend_yield": 2.9, "payout_ratio": 0.58, "latest_ffo_per_share": 6.15},
    {"ticker": "SPG", "name": "Simon Property Group", "sector": REITSector.RETAIL, "sub_sector": "Mall",
     "market_cap": 55_000_000_000, "ipo_year": 1993, "property_count": 232,
     "total_sqft": 186_000_000, "geographic_focus": "US & International",
     "dividend_yield": 4.5, "payout_ratio": 0.68, "latest_ffo_per_share": 12.30},
    {"ticker": "EQIX", "name": "Equinix", "sector": REITSector.DATA_CENTER, "sub_sector": "Colocation",
     "market_cap": 80_000_000_000, "ipo_year": 2015, "property_count": 260,
     "total_sqft": 65_000_000, "geographic_focus": "Global",
     "dividend_yield": 2.1, "payout_ratio": 0.48, "latest_ffo_per_share": 33.50},
    {"ticker": "PSB", "name": "Public Storage", "sector": REITSector.SPECIALTY, "sub_sector": "Self Storage",
     "market_cap": 42_000_000_000, "ipo_year": 1995, "property_count": 3000,
     "total_sqft": 250_000_000, "geographic_focus": "US & Europe",
     "dividend_yield": 4.2, "payout_ratio": 0.70, "latest_ffo_per_share": 14.20},
    {"ticker": "AVB", "name": "AvalonBay Communities", "sector": REITSector.RESIDENTIAL, "sub_sector": "Apartment",
     "market_cap": 28_000_000_000, "ipo_year": 1994, "property_count": 295,
     "total_sqft": 95_000_000, "geographic_focus": "US Coastal",
     "dividend_yield": 3.1, "payout_ratio": 0.64, "latest_ffo_per_share": 12.85},
    {"ticker": "WELL", "name": "Welltower", "sector": REITSector.HEALTHCARE, "sub_sector": "Senior Housing",
     "market_cap": 35_000_000_000, "ipo_year": 2010, "property_count": 2200,
     "total_sqft": 180_000_000, "geographic_focus": "US, UK, Canada",
     "dividend_yield": 2.7, "payout_ratio": 0.55, "latest_ffo_per_share": 3.65},
    {"ticker": "DLR", "name": "Digital Realty", "sector": REITSector.DATA_CENTER, "sub_sector": "Data Center",
     "market_cap": 48_000_000_000, "ipo_year": 2004, "property_count": 310,
     "total_sqft": 55_000_000, "geographic_focus": "Global",
     "dividend_yield": 3.2, "payout_ratio": 0.60, "latest_ffo_per_share": 7.40},
    {"ticker": "VICI", "name": "VICI Properties", "sector": REITSector.SPECIALTY, "sub_sector": "Gaming",
     "market_cap": 33_000_000_000, "ipo_year": 2018, "property_count": 93,
     "total_sqft": 140_000_000, "geographic_focus": "US",
     "dividend_yield": 5.2, "payout_ratio": 0.74, "latest_ffo_per_share": 2.25},
    {"ticker": "CCI", "name": "Crown Castle", "sector": REITSector.INFRASTRUCTURE, "sub_sector": "Tower/Fiber",
     "market_cap": 38_000_000_000, "ipo_year": 2014, "property_count": 40800,
     "total_sqft": 0, "geographic_focus": "US",
     "dividend_yield": 6.5, "payout_ratio": 0.82, "latest_ffo_per_share": 9.10},
    {"ticker": "AMH", "name": "American Homes 4 Rent", "sector": REITSector.RESIDENTIAL, "sub_sector": "Single Family",
     "market_cap": 15_000_000_000, "ipo_year": 2013, "property_count": 59000,
     "total_sqft": 120_000_000, "geographic_focus": "US Sun Belt",
     "dividend_yield": 2.4, "payout_ratio": 0.50, "latest_ffo_per_share": 1.95},
]


@dataclass
class REIT:
    """Master data for a Real Estate Investment Trust."""

    ticker: str
    name: str
    sector: REITSector
    sub_sector: str = ""
    market_cap: float = 0.0
    ipo_year: Optional[int] = None
    property_count: int = 0
    total_sqft: float = 0.0
    geographic_focus: str = ""
    dividend_yield: float = 0.0
    payout_ratio: float = 0.0
    latest_ffo_per_share: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # --- Validation ---

    def __post_init__(self) -> None:
        self.ticker = self.ticker.strip().upper()
        if not self.ticker:
            raise ValueError("REIT ticker must be non-empty")
        if self.payout_ratio < 0 or self.payout_ratio > 2.0:
            raise ValueError(f"Payout ratio {self.payout_ratio} out of valid range [0, 2.0]")
        if self.market_cap < 0:
            raise ValueError("Market cap must be non-negative")

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize REIT to dictionary."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector.value if isinstance(self.sector, REITSector) else self.sector,
            "sub_sector": self.sub_sector,
            "market_cap": self.market_cap,
            "ipo_year": self.ipo_year,
            "property_count": self.property_count,
            "total_sqft": self.total_sqft,
            "geographic_focus": self.geographic_focus,
            "dividend_yield": self.dividend_yield,
            "payout_ratio": self.payout_ratio,
            "latest_ffo_per_share": self.latest_ffo_per_share,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> REIT:
        """Deserialize REIT from dictionary."""
        if "sector" in data and isinstance(data["sector"], str):
            data["sector"] = REITSector(data["sector"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Class Methods ---

    @classmethod
    def create_seed_reits(cls) -> List[REIT]:
        """Create all 12 seed REITs."""
        return [cls(**seed) for seed in SEED_REITS]

    @classmethod
    def get_by_ticker(cls, ticker: str, reits: Optional[List[REIT]] = None) -> Optional[REIT]:
        """Find a REIT by ticker from a list (or seed data)."""
        reits = reits or cls.create_seed_reits()
        ticker = ticker.strip().upper()
        for reit in reits:
            if reit.ticker == ticker:
                return reit
        return None

    @classmethod
    def get_by_sector(cls, sector: REITSector, reits: Optional[List[REIT]] = None) -> List[REIT]:
        """Get all REITs in a given sector."""
        reits = reits or cls.create_seed_reits()
        return [r for r in reits if r.sector == sector]

    # --- Derived Metrics ---

    @property
    def annual_dividend_per_share(self) -> float:
        """Estimate annual dividend per share from FFO and payout ratio."""
        if self.latest_ffo_per_share <= 0:
            return 0.0
        return self.latest_ffo_per_share * self.payout_ratio

    @property
    def ffo_yield(self) -> float:
        """FFO yield (inverse of P/FFO)."""
        if self.market_cap <= 0 or self.latest_ffo_per_share <= 0:
            return 0.0
        shares = self.market_cap / self.latest_ffo_per_share * self.payout_ratio
        if shares <= 0:
            return 0.0
        return self.latest_ffo_per_share / (self.market_cap / shares)

    def __repr__(self) -> str:
        return f"REIT(ticker={self.ticker!r}, name={self.name!r}, sector={self.sector.value})"
