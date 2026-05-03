"""
Property domain model — individual property or portfolio records within a REIT.

Tracks property type, location (MSA-level), occupancy, rental income,
lease terms, and valuation metrics for each asset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional


class PropertyType(str, Enum):
    """Property type classifications."""
    RETAIL = "Retail"
    OFFICE = "Office"
    INDUSTRIAL_LOGISTICS = "Industrial/Logistics"
    APARTMENT = "Apartment"
    SINGLE_FAMILY = "Single Family"
    HEALTHCARE = "Healthcare"
    DATA_CENTER = "Data Center"
    TOWER = "Tower"
    SELF_STORAGE = "Self Storage"
    HOSPITALITY = "Hospitality"
    MIXED_USE = "Mixed Use"


class PropertyStatus(str, Enum):
    """Operational status of a property."""
    OPERATING = "Operating"
    DEVELOPMENT = "Development"
    REDEVELOPMENT = "Redevelopment"
    VACANT = "Vacant"
    SOLD = "Sold"


@dataclass
class Property:
    """Individual property record within a REIT portfolio."""

    property_id: str
    reit_ticker: str
    name: str
    property_type: PropertyType = PropertyType.RETAIL
    status: PropertyStatus = PropertyStatus.OPERATING
    address: str = ""
    city: str = ""
    state: str = ""
    msa: str = ""
    sqft: float = 0.0
    occupancy_rate: float = 0.0
    annual_rent_psf: float = 0.0
    lease_expiry_weighted_avg: float = 0.0
    cap_rate: float = 0.0
    acquisition_date: Optional[str] = None
    acquisition_cost: float = 0.0
    current_book_value: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)

    # --- Validation ---

    def __post_init__(self) -> None:
        self.reit_ticker = self.reit_ticker.strip().upper()
        if not self.property_id:
            raise ValueError("Property ID must be non-empty")
        if not self.reit_ticker:
            raise ValueError("REIT ticker must be non-empty")
        if not (0.0 <= self.occupancy_rate <= 1.0):
            raise ValueError(f"Occupancy rate {self.occupancy_rate} must be in [0, 1]")
        if self.sqft < 0:
            raise ValueError("Square footage must be non-negative")
        if self.cap_rate < 0 or self.cap_rate > 0.20:
            raise ValueError(f"Cap rate {self.cap_rate} out of expected range [0, 0.20]")

    # --- Serialization ---

    def to_dict(self) -> Dict:
        """Serialize Property to dictionary."""
        return {
            "property_id": self.property_id,
            "reit_ticker": self.reit_ticker,
            "name": self.name,
            "property_type": self.property_type.value,
            "status": self.status.value,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "msa": self.msa,
            "sqft": self.sqft,
            "occupancy_rate": self.occupancy_rate,
            "annual_rent_psf": self.annual_rent_psf,
            "lease_expiry_weighted_avg": self.lease_expiry_weighted_avg,
            "cap_rate": self.cap_rate,
            "acquisition_date": self.acquisition_date,
            "acquisition_cost": self.acquisition_cost,
            "current_book_value": self.current_book_value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> Property:
        """Deserialize Property from dictionary."""
        if "property_type" in data and isinstance(data["property_type"], str):
            data["property_type"] = PropertyType(data["property_type"])
        if "status" in data and isinstance(data["status"], str):
            data["status"] = PropertyStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # --- Derived Metrics ---

    @property
    def annual_rent(self) -> float:
        """Estimated annual rental income for the property."""
        return self.sqft * self.annual_rent_psf

    @property
    def noi_estimate(self) -> float:
        """Estimated NOI (simplified: rent × occupancy × (1 - vacancy/expense))."""
        expense_ratio = 0.35
        return self.annual_rent * self.occupancy_rate * (1 - expense_ratio)

    @property
    def value_cap(self) -> float:
        """Implied value using cap rate."""
        if self.cap_rate <= 0:
            return 0.0
        return self.noi_estimate / self.cap_rate

    @property
    def appreciation(self) -> float:
        """Simple appreciation/depreciation from acquisition to book value."""
        if self.acquisition_cost <= 0:
            return 0.0
        return (self.current_book_value - self.acquisition_cost) / self.acquisition_cost

    def __repr__(self) -> str:
        return f"Property(id={self.property_id!r}, ticker={self.reit_ticker}, name={self.name!r})"
