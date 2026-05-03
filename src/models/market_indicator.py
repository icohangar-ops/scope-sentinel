"""
MarketIndicator domain model — macro-economic indicators from FRED.

Tracks interest rates, mortgage rates, CPI, housing price indices,
unemployment, construction activity, and other macro data relevant to REITs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


class FREDIndicator:
    """FRED indicator constants and metadata."""

    FEDFUNDS = {"series_id": "FEDFUNDS", "name": "Federal Funds Effective Rate", "frequency": "Monthly", "unit": "Percent"}
    WFII = {"series_id": "WFII", "name": "30-Year Fixed Rate Mortgage Average", "frequency": "Weekly", "unit": "Percent"}
    CPIAUCSL = {"series_id": "CPIAUCSL", "name": "Consumer Price Index (Urban)", "frequency": "Monthly", "unit": "Index"}
    USSTHPI = {"series_id": "USSTHPI", "name": "U.S. National Home Price Index", "frequency": "Quarterly", "unit": "Index"}
    UNRATE = {"series_id": "UNRATE", "name": "Unemployment Rate", "frequency": "Monthly", "unit": "Percent"}
    TTLCONS = {"series_id": "TTLCONS", "name": "Total Construction Spending", "frequency": "Monthly", "unit": "Billions USD"}
    PERMIT = {"series_id": "PERMIT", "name": "New Private Housing Building Permits", "frequency": "Monthly", "unit": "Thousands"}
    DGS10 = {"series_id": "DGS10", "name": "10-Year Treasury Constant Maturity Rate", "frequency": "Daily", "unit": "Percent"}
    DGS2 = {"series_id": "DGS2", "name": "2-Year Treasury Constant Maturity Rate", "frequency": "Daily", "unit": "Percent"}
    MSPUS = {"series_id": "MSPUS", "name": "Median Sales Price of Houses Sold", "frequency": "Monthly", "unit": "USD"}
    HOUST = {"series_id": "HOUST", "name": "New Privately-Owned Housing Units Started", "frequency": "Monthly", "unit": "Thousands"}

    @classmethod
    def all_indicators(cls) -> Dict[str, Dict]:
        """Return all FRED indicator definitions."""
        return {
            attr: getattr(cls, attr)
            for attr in dir(cls)
            if not attr.startswith("_") and isinstance(getattr(cls, attr), dict)
        }

    @classmethod
    def get_reit_relevant(cls) -> List[Dict]:
        """Return indicators most relevant to REIT analysis."""
        return [
            cls.FEDFUNDS, cls.WFII, cls.DGS10, cls.DGS2,
            cls.CPIAUCSL, cls.USSTHPI, cls.UNRATE,
            cls.TTLCONS, cls.PERMIT, cls.HOUST,
        ]


@dataclass
class MarketIndicator:
    """A single macro-economic data point from FRED or similar source."""

    indicator_id: str
    series_id: str
    name: str
    date: str
    value: float
    unit: str = ""
    frequency: str = ""
    source: str = "FRED"
    created_at: datetime = field(default_factory=datetime.utcnow)

    # --- Validation ---

    def __post_init__(self) -> None:
        if not self.series_id:
            raise ValueError("Series ID must be non-empty")
        if not self.date:
            raise ValueError("Date must be non-empty")

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "indicator_id": self.indicator_id,
            "series_id": self.series_id,
            "name": self.name,
            "date": self.date,
            "value": self.value,
            "unit": self.unit,
            "frequency": self.frequency,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> MarketIndicator:
        """Deserialize from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Class Methods ---

    @classmethod
    def build_id(cls, series_id: str, date: str) -> str:
        """Generate deterministic indicator ID."""
        return f"{series_id}_{date}".replace("-", "")

    @classmethod
    def from_fred_response(cls, series_id: str, date: str, value: float) -> MarketIndicator:
        """Create from a FRED API response row."""
        all_indicators = FREDIndicator.all_indicators()
        meta = all_indicators.get(series_id, {})
        return cls(
            indicator_id=cls.build_id(series_id, date),
            series_id=series_id,
            name=meta.get("name", series_id),
            date=date,
            value=value,
            unit=meta.get("unit", ""),
            frequency=meta.get("frequency", ""),
        )

    # --- Derived Methods ---

    def __repr__(self) -> str:
        return f"MarketIndicator(series={self.series_id!r}, date={self.date!r}, value={self.value})"
